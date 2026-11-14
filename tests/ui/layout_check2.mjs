import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.goto("http://127.0.0.1:7860", { waitUntil: "networkidle" });
await p.locator("nav >> text=语音编辑").first().click();
await p.waitForTimeout(900);
// 提交按钮无需滚动即可见
const btn = p.locator("button", { hasText: "生成候选音频" }).first();
const btnInView = await btn.evaluate(el => { const r = el.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0 && r.height > 0; });
console.log("生成按钮常驻可见:", btnInView ? "✓" : "✗");
await p.screenshot({ path: "screenshots-studio/40-layout-edit-empty.png" });
// 加载音频 → dock 折叠头可见
await p.locator("button", { hasText: "最近上传" }).first().click();
await p.waitForTimeout(400);
await p.locator("main >> text=01-normal.wav").first().click();
await p.waitForTimeout(2200);
await p.screenshot({ path: "screenshots-studio/41-layout-edit-audio.png" });
const dock = p.locator("button", { hasText: "生成结果" }).first();
console.log("dock头可见:", await dock.isVisible() ? "✓" : "✗");
for (let i = 0; i < 3; i++) { if ((await dock.getAttribute("aria-expanded")) === "true") break; await dock.click(); await p.waitForTimeout(1000); }
await p.waitForTimeout(1800);
await p.screenshot({ path: "screenshots-studio/42-layout-results-dock.png" });
// TTS：无原始音频区 + dock 收起
await p.locator("nav >> text=文本转语音").first().click();
await p.waitForTimeout(900);
const ttsText = await p.locator("main").innerText();
console.log("TTS无原始音频stage:", !ttsText.includes("最近上传") ? "✓" : "✗");
console.log("TTS参考音色在:", ttsText.includes("参考音色") ? "✓" : "✗");
const ttsBtnInView = await btn.evaluate(el => { const r = el.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0; });
console.log("TTS生成按钮可见:", ttsBtnInView ? "✓" : "✗");
await p.screenshot({ path: "screenshots-studio/43-layout-tts.png" });
// 窄窗：studio 根容器内部滚动
await p.setViewportSize({ width: 900, height: 800 });
await p.locator("nav >> text=语音编辑").first().click();
await p.waitForTimeout(800);
const rootScroll = await p.evaluate(() => {
  const el = document.querySelector("main > div > div");
  return el ? el.scrollHeight > el.clientHeight + 2 : false;
});
console.log("窄窗内部可滚动:", rootScroll ? "✓" : "✗");
await p.screenshot({ path: "screenshots-studio/45-layout-narrow.png" });
await b.close();
