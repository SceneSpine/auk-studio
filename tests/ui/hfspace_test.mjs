import { chromium } from "playwright";
import fs from "fs"; import path from "path";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const BASE = process.env.AUK_TEST_BASE || "http://127.0.0.1:7860";
const SHOTS = path.join(HERE, "screenshots-studio");
const results = [];
const check = (n, ok, d="") => { results.push({n, ok, d}); console.log(`${ok?"✓":"✗"} ${n}${d?" — "+d:""}`); };
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const errs = []; p.on("pageerror", e => errs.push(e.message));
try {
  await p.goto(BASE, { waitUntil: "networkidle" });
  await p.locator("nav >> text=模型管理").first().click(); await p.waitForTimeout(900);
  await p.locator("button", { hasText: /添加|新建|新增/ }).first().click(); await p.waitForTimeout(500);
  const dlg = p.locator('[role="dialog"]');
  // 类型选择 → HF Space
  const kindSel = dlg.locator("select").first();
  const opts = await kindSel.locator("option").allTextContents();
  const hfIdx = opts.findIndex(o => /HuggingFace|HF|Space/.test(o));
  check("类型选择含 HF Space", hfIdx >= 0, opts.join("|"));
  await kindSel.selectOption({ index: hfIdx }); await p.waitForTimeout(400);
  // 官方预设按钮
  const presetBtn = dlg.locator("button", { hasText: /官方|tencent/ }).first();
  check("官方预设按钮", await presetBtn.count() > 0);
  if (await presetBtn.count()) {
    await presetBtn.click(); await p.waitForTimeout(300);
    const urlVal = await dlg.locator("input").nth(1).inputValue();
    check("预设填入官方 Space 地址", urlVal.includes("tencent-auk.hf.space"), urlVal);
  }
  // 改为 mock 地址做全链路
  await dlg.locator("input").nth(0).fill("HF Space 测试");
  await dlg.locator("input").nth(1).fill("http://127.0.0.1:7912");
  await p.screenshot({ path: path.join(SHOTS, "54-hfspace-form.png") });
  await dlg.locator("button", { hasText: /保存|创建|确定|添加/ }).last().click(); await p.waitForTimeout(900);
  check("HF Space provider 创建", (await p.locator("main").innerText()).includes("HF Space 测试"));
  // 连通测试
  const testBtn = p.locator("button", { hasText: /测试/ }).first();
  if (await testBtn.count()) { await testBtn.click(); await p.waitForTimeout(2500);
    check("HF Space 连通测试", /连通|成功|\d+ms|ok/i.test(await p.locator("body").innerText())); }
  // Studio：选 HF Space → 音色设计模式提交 instruct_tts
  await p.locator("nav >> text=音色设计").first().click(); await p.waitForTimeout(800);
  const provSel = p.locator("main select").first();
  const pOpts = await provSel.locator("option").allTextContents();
  const rIdx = pOpts.findIndex(o => o.includes("HF Space 测试"));
  check("ConfigPanel 含 HF Space", rIdx >= 0);
  if (rIdx >= 0) {
    await provSel.selectOption({ index: rIdx }); await p.waitForTimeout(700);
    const st = await p.locator("main").innerText();
    check("HF Space 隐私提示（共享演示）", /HuggingFace|Space|共享|排队/.test(st));
    check("HF Space 全模式（音色设计可用）", /音色描述|描述/.test(st));
    await p.screenshot({ path: path.join(SHOTS, "55-hfspace-studio.png") });
    const tas = p.locator("main textarea");
    await tas.nth(0).fill("一位平静自然的女性声音，语速适中。");
    await tas.nth(1).fill("这是通过 HF Space 协议生成的测试语音。");
    await p.locator("button", { hasText: /生成候选/ }).first().click();
    let done = false;
    for (let i = 0; i < 50; i++) { await p.waitForTimeout(1500);
      const t = await p.locator("main").innerText();
      if (/已完成/.test(t) && !/生成中|推理中|排队中|准备中|加载模型/.test(t)) { done = true; break; }
      if (/任务失败|重试/.test(t)) break; }
    check("HF Space mock 任务完成", done);
    await p.screenshot({ path: path.join(SHOTS, "56-hfspace-result.png") });
    check("结果含 HF Space 徽章", /HF Space/.test(await p.locator("main").innerText()));
  }
  check("无页面 JS 错误", errs.length === 0, errs.slice(0,3).join(" | "));
} catch (e) { check("测试执行异常", false, String(e).slice(0,300)); await p.screenshot({ path: path.join(SHOTS, "59-hfspace-error.png") }); }
finally { await b.close(); }
const passed = results.filter(r=>r.ok).length;
console.log(`\n${passed}/${results.length} 通过`);
fs.writeFileSync(path.join(SHOTS, "hfspace-results.json"), JSON.stringify({passed, total: results.length, results}, null, 2));
process.exit(passed === results.length ? 0 : 1);
