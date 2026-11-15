// AuK Studio Provider 功能验收（需先起 mock TTS：.venv-auk/bin/python tests/api/mock_tts.py --port 7911）
// 用法：node tests/ui/provider_test.mjs
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const BASE = process.env.AUK_TEST_BASE || "http://127.0.0.1:7860";
const SHOTS = path.join(HERE, "screenshots-studio");
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "✓" : "✗"} ${name}${detail ? " — " + detail : ""}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(e.message));

try {
  await page.goto(BASE, { waitUntil: "networkidle" });

  // 1. 模型管理页 → Provider 区
  await page.locator("nav >> text=模型管理").first().click();
  await page.waitForTimeout(900);
  const modelsText = await page.locator("main").innerText();
  check("Models 页有 Provider 区", /Provider|推理服务|在线/.test(modelsText));
  check("本地 MLX 内置项", modelsText.includes("本地"));
  await page.screenshot({ path: path.join(SHOTS, "50-providers.png") });

  // 2. 新建在线 provider（mock）
  const addBtn = page.locator("button", { hasText: /新建|添加|配置在线|新增/ }).first();
  await addBtn.click();
  await page.waitForTimeout(500);
  const dlg = page.locator('[role="dialog"]');
  check("新建 provider 弹窗", await dlg.isVisible());
  // 名称
  await dlg.locator("input").nth(0).fill("Mock 在线 TTS");
  // 找 base_url / api_key / model / voice 输入（按 placeholder/label 灵活定位）
  const inputs = dlg.locator("input");
  const n = await inputs.count();
  // 预设选择（若有）：选自定义确保 base_url 可填
  const presetSel = dlg.locator("select").first();
  if (await presetSel.count()) {
    const opts = await presetSel.locator("option").allTextContents();
    const customIdx = opts.findIndex((o) => /自定义|custom/i.test(o));
    if (customIdx >= 0) await presetSel.selectOption({ index: customIdx });
  }
  // 逐个 input 按实际 placeholder 填写（name/baseUrl/key/model/voice）
  for (let i = 0; i < n; i++) {
    const ph = ((await inputs.nth(i).getAttribute("placeholder")) || "").toLowerCase();
    const type = await inputs.nth(i).getAttribute("type");
    if (ph.includes("example.com")) await inputs.nth(i).fill("http://127.0.0.1:7911/v1");
    else if (type === "password" || ph.includes("sk-")) await inputs.nth(i).fill("sk-mock-test-key-123456");
    else if (ph.includes("gpt-4o")) await inputs.nth(i).fill("mock-tts");
    else if (ph.includes("alloy") || ph.includes("音色 id")) await inputs.nth(i).fill("alloy");
  }
  await page.screenshot({ path: path.join(SHOTS, "51-provider-form.png") });
  await dlg.locator("button", { hasText: /保存|创建|确定|添加/ }).last().click();
  await page.waitForTimeout(900);
  const afterAdd = await page.locator("main").innerText();
  check("provider 创建成功", afterAdd.includes("Mock 在线 TTS"));
  check("key 已掩码（不明文）", !afterAdd.includes("sk-mock-test-key-123456"));

  // 3. 测试连通
  const testBtn = page.locator("button", { hasText: /测试/ }).first();
  if (await testBtn.count()) {
    await testBtn.click();
    await page.waitForTimeout(3000);
    const t = await page.locator("body").innerText(); // toast 在 main 之外
    check("provider 连通测试", /连通|成功|\d+ms|ok/i.test(t));
  }

  // 4. Studio：选择在线 provider → 模式门禁 + 隐私提示
  await page.locator("nav >> text=语音编辑").first().click();
  await page.waitForTimeout(800);
  const provSel = page.locator("main select").first();
  const selOpts = await provSel.locator("option").allTextContents();
  const onlineIdx = selOpts.findIndex((o) => o.includes("Mock"));
  check("ConfigPanel 有 provider 选择", onlineIdx >= 0, selOpts.join("|"));
  if (onlineIdx >= 0) {
    await provSel.selectOption({ index: onlineIdx });
    await page.waitForTimeout(800);
    const studioText = await page.locator("main").innerText();
    check("在线隐私提示", /发送至|第三方|127\.0\.0\.1:7911/.test(studioText));
    check("自动切到 TTS 模式", studioText.includes("朗读文本") || studioText.includes("文本转语音"));
    await page.screenshot({ path: path.join(SHOTS, "52-studio-online.png") });

    // 5. 提交在线 TTS 任务
    const ta = page.locator("main textarea").first();
    await ta.fill("你好，这是在线接口生成的语音。");
    await page.waitForTimeout(300);
    await page.locator("button", { hasText: /生成候选/ }).first().click();
    let completed = false;
    for (let i = 0; i < 40; i++) {
      await page.waitForTimeout(1500);
      const t = await page.locator("main").innerText();
      if (/已完成|完成/.test(t) && !/推理中|排队/.test(t)) { completed = true; break; }
      if (/失败/.test(t)) break;
    }
    check("在线 TTS 任务完成", completed);
    await page.screenshot({ path: path.join(SHOTS, "53-online-result.png") });
    const resText = await page.locator("main").innerText();
    check("结果含在线 provider 徽章", /在线|Mock/.test(resText));
  }

  // 6. 切回本地：模式恢复可用
  const backIdx = selOpts.findIndex((o) => /本地|local/i.test(o));
  if (backIdx >= 0) {
    await provSel.selectOption({ index: backIdx });
    await page.waitForTimeout(600);
    const t = await page.locator("main").innerText();
    check("切回本地恢复编辑模式", /台词编辑|局部替换|原片段/.test(t));
  }

  check("无页面 JS 错误", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));
} catch (e) {
  check("测试执行异常", false, String(e).slice(0, 300));
  await page.screenshot({ path: path.join(SHOTS, "59-provider-error.png") });
} finally {
  await browser.close();
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 通过`);
fs.writeFileSync(path.join(SHOTS, "provider-results.json"), JSON.stringify({ passed, total: results.length, results }, null, 2));
process.exit(passed === results.length ? 0 : 1);