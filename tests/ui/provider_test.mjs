// AuK Studio 远程 AuK Provider 验收
// 前置：起一个"远程"AuK Studio 实例：AUK_DATA_DIR=/tmp/auk-remote-ui AUK_PORT=7862 .venv-auk/bin/python -m app.backend.main
// 用法：node tests/ui/provider_test.mjs  （AUK_REMOTE_TEST_URL 可覆盖远程地址）
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const BASE = process.env.AUK_TEST_BASE || "http://127.0.0.1:7860";
const REMOTE = process.env.AUK_REMOTE_TEST_URL || "http://127.0.0.1:7862";
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

  // 1. Models 页 Provider 区
  await page.locator("nav >> text=模型管理").first().click();
  await page.waitForTimeout(900);
  const modelsText = await page.locator("main").innerText();
  check("Models 页有 Provider 区", /Provider|推理/.test(modelsText));
  check("本地 MLX 内置项", modelsText.includes("本地"));
  await page.screenshot({ path: path.join(SHOTS, "50-providers.png") });

  // 2. 添加远程 AuK 服务（简化表单：名称/Base URL/可选 Key）
  await page.locator("button", { hasText: /添加|新建|新增/ }).first().click();
  await page.waitForTimeout(500);
  const dlg = page.locator('[role="dialog"]');
  check("添加远程服务弹窗", await dlg.isVisible());
  const dlgText = await dlg.innerText();
  check("无 OpenAI/硅基等非 AuK 预设", !/OpenAI|硅基|SiliconFlow/.test(dlgText));
  const inputs = dlg.locator("input");
  await inputs.nth(0).fill("远程 AuK 测试");
  await inputs.nth(1).fill(REMOTE);
  const n = await inputs.count();
  if (n > 2) await inputs.nth(2).fill("test-token-abcdef123456"); // 可选 key，验证掩码
  // 连续输入不失焦（Dialog 修复回归）
  await inputs.nth(0).click();
  await inputs.nth(0).pressSequentially("XYZ", { delay: 50 });
  const nameVal = await inputs.nth(0).inputValue();
  check("表单连续输入不失焦", nameVal.endsWith("XYZ"), nameVal);
  await inputs.nth(0).fill("远程 AuK 测试");
  await page.screenshot({ path: path.join(SHOTS, "51-provider-form.png") });
  await dlg.locator("button", { hasText: /保存|创建|确定|添加/ }).last().click();
  await page.waitForTimeout(900);
  const afterAdd = await page.locator("main").innerText();
  check("远程服务创建成功", afterAdd.includes("远程 AuK 测试"));
  check("key 已掩码", !afterAdd.includes("test-token-abcdef123456"));

  // 3. 连通测试
  const testBtn = page.locator("button", { hasText: /测试/ }).first();
  if (await testBtn.count()) {
    await testBtn.click();
    await page.waitForTimeout(3000);
    const t = await page.locator("body").innerText();
    check("远程服务连通测试", /连通|成功|\d+ms|ok/i.test(t));
  }

  // 4. Studio：选远程 → 全模式可用 + 音频隐私提示
  await page.locator("nav >> text=语音编辑").first().click();
  await page.waitForTimeout(800);
  // 装载音频（最近上传弹层）
  await page.locator("button", { hasText: "最近上传" }).first().click();
  await page.waitForTimeout(400);
  await page.locator("main >> text=01-normal.wav").first().click();
  await page.waitForTimeout(2000);
  const provSel = page.locator("main select").first();
  const selOpts = await provSel.locator("option").allTextContents();
  const remoteIdx = selOpts.findIndex((o) => o.includes("远程 AuK 测试"));
  check("ConfigPanel 有远程 provider", remoteIdx >= 0, selOpts.join("|"));
  if (remoteIdx >= 0) {
    await provSel.selectOption({ index: remoteIdx });
    await page.waitForTimeout(800);
    const studioText = await page.locator("main").innerText();
    check("远程隐私提示（音频与文本）", /音频与文本|音频.*发送/.test(studioText));
    check("远程保留编辑模式（全能力）", /原片段|局部替换/.test(studioText));
    await page.screenshot({ path: path.join(SHOTS, "52-studio-remote.png") });

    // 5. 远程 replace 任务（真实穿透推理）
    const orig = page.locator('input[placeholder*="明天的会议"]').first();
    const rep = page.locator('input[placeholder*="明天的发布会"]').first();
    await orig.fill("会议室");
    await rep.fill("发布会");
    await page.locator("button", { hasText: /生成候选/ }).first().click();
    let completed = false;
    for (let i = 0; i < 100; i++) {
      await page.waitForTimeout(2000);
      const t = await page.locator("main").innerText();
      if (/已完成/.test(t) && !/生成中|推理中|排队中|准备中|加载模型/.test(t)) { completed = true; break; }
      if (/任务失败|重试/.test(t)) break;
    }
    check("远程 replace 任务完成", completed);
    await page.screenshot({ path: path.join(SHOTS, "53-remote-result.png") });
    const resText = await page.locator("main").innerText();
    check("结果含远程 AuK 徽章", /远程 AuK/.test(resText));
  }

  // 6. 切回本地
  const backIdx = selOpts.findIndex((o) => /本地/.test(o));
  if (backIdx >= 0) {
    await provSel.selectOption({ index: backIdx });
    await page.waitForTimeout(600);
    const t = await page.locator("main").innerText();
    check("切回本地正常", /原片段|局部替换|生成配置/.test(t));
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