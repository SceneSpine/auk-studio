// AuK Studio UI 验收测试（Playwright 无头浏览器）
// 用法：node tests/ui/studio_test.mjs [--full]
//   默认：全部页面导航 / 真实数据渲染 / 浅深主题 / 1440×900 与 1280×800 截图 / 空态错误态
//   --full：上传音频 + 提交真实编辑任务并等待完成 + 结果区 + 音色库授权流程
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const ROOT = path.resolve(HERE, "../..");
const BASE = process.env.AUK_TEST_BASE || "http://127.0.0.1:7860";
const FULL = process.argv.includes("--full");
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

async function nav(label) {
  await page.locator(`nav >> text=${label}`).first().click();
  await page.waitForTimeout(700);
}
async function shot(name) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

try {
  // 1. 加载与品牌
  await page.goto(BASE, { waitUntil: "networkidle" });
  check("页面加载", await page.locator("text=AuK Studio").first().isVisible());
  check("非官方声明可见", await page.locator("text=Unofficial").first().isVisible());
  await shot("01-dashboard");

  // 2. 仪表盘真实数据
  const dashText = await page.locator("main").innerText();
  check("仪表盘资源摘要", /GB/.test(dashText), "显示真实磁盘/内存数值");
  check("仪表盘快捷创作", dashText.includes("台词编辑") && dashText.includes("文本转语音"));
  check("仪表盘最近任务区", dashText.includes("最近任务") || dashText.includes("任务"));

  // 3. 导航全部页面
  const pages = [
    ["语音编辑", "02-studio-edit"],
    ["文本转语音", "03-studio-tts"],
    ["音色设计", "04-studio-design"],
    ["音色库", "05-voices"],
    ["模型管理", "06-models"],
    ["环境检测", "07-system"],
    ["任务历史", "08-jobs"],
    ["设置", "09-settings"],
    ["关于", "10-about"],
  ];
  for (const [label, name] of pages) {
    await nav(label);
    const visible = await page.locator("main").isVisible();
    check(`导航 ${label}`, visible);
    await shot(name);
  }

  // 4. 模型管理真实状态
  await nav("模型管理");
  const modelsText = await page.locator("main").innerText();
  check("模型页显示 Flash", /Flash/i.test(modelsText));
  check("模型页显示 Qwen 非商用披露", /非商用|Research/i.test(modelsText));
  check("模型页已就绪状态", /已就绪|就绪/.test(modelsText));

  // 5. 环境检测真实探针
  await nav("环境检测");
  const sysText = await page.locator("main").innerText();
  check("环境检测显示检查项", /Metal|内存|磁盘/.test(sysText));
  check("环境检测有就绪判定", /Ready|Caution|Blocked|就绪|风险|阻断|正常/.test(sysText));

  // 6. 关于页许可披露
  await nav("关于");
  const aboutText = await page.locator("main").innerText();
  check("关于页非官方声明", /not affiliated|非官方|不存在官方关联/.test(aboutText));
  check("关于页 Qwen Research 披露", /Research License|非商业/.test(aboutText));
  check("关于页快捷键帮助", /Space|Cmd/.test(aboutText));

  // 7. 设置页
  await nav("设置");
  const settingsText = await page.locator("main").innerText();
  check("设置页主题/默认参数", /主题|精度|默认/.test(settingsText));

  // 8. 深色模式
  await page.locator('button[aria-label*="深色"]').first().click();
  await page.waitForTimeout(400);
  const isDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  check("深色模式切换", isDark);
  await nav("概览");
  await shot("11-dashboard-dark");
  await nav("语音编辑");
  await shot("12-studio-dark");
  await page.locator('button[aria-label*="浅色"]').first().click();
  await page.waitForTimeout(300);

  // 9. 1280×800 响应式
  await page.setViewportSize({ width: 1280, height: 800 });
  await nav("概览");
  await shot("13-dashboard-1280");
  await nav("语音编辑");
  await shot("14-studio-1280");
  const overflow1280 = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
  check("1280 无横向溢出", !overflow1280);
  await page.setViewportSize({ width: 1440, height: 900 });

  // 10. 窄窗（导航抽屉）
  await page.setViewportSize({ width: 900, height: 800 });
  await page.waitForTimeout(400);
  await shot("15-narrow");
  const drawerBtn = page.locator('button[aria-label="打开导航"]');
  check("窄窗导航抽屉按钮", await drawerBtn.isVisible());
  await drawerBtn.click();
  await page.waitForTimeout(300);
  check("窄窗抽屉可打开", await page.locator("nav >> text=模型管理").last().isVisible());
  await shot("16-narrow-drawer");
  await page.keyboard.press("Escape");
  await page.locator("body").click({ position: { x: 800, y: 400 } });
  await page.setViewportSize({ width: 1440, height: 900 });

  // 11. 任务历史（真实历史数据）
  await nav("任务历史");
  const jobsText = await page.locator("main").innerText();
  check("任务历史渲染", /任务|排队|已完成|失败/.test(jobsText));

  if (FULL) {
    // 12. 完整创作流程
    await nav("语音编辑");
    await page.locator('input[type="file"]').first().setInputFiles(path.join(ROOT, "data/test-set/01-normal.wav"));
    await page.waitForTimeout(2500);
    const upText = await page.locator("main").innerText();
    check("上传音频显示信息", upText.includes("01-normal"));
    await shot("20-uploaded");

    // 填写局部替换（实际 placeholder：例如：明天的会议 / 例如：明天的发布会）
    const orig = page.locator('input[placeholder*="明天的会议"]').first();
    const rep = page.locator('input[placeholder*="明天的发布会"]').first();
    if (await orig.count()) {
      await orig.fill("会议室");
      await rep.fill("发布会");
    } else {
      const inputs = page.locator("main input:not([type]), main input[type='text'], main textarea");
      await inputs.nth(0).fill("会议室");
      await inputs.nth(1).fill("发布会");
    }
    await shot("21-form-filled");

    // 提交（Cmd+Enter 或按钮）
    const genBtn = page.locator("button", { hasText: /生成候选|生成/ }).first();
    await genBtn.click();
    await page.waitForTimeout(1500);
    const runText = await page.locator("main").innerText();
    check("任务提交并显示进度", /排队|准备|加载|推理|推理中/.test(runText));
    await shot("22-job-running");

    // 等待完成（最长 180s）
    let completed = false;
    for (let i = 0; i < 90; i++) {
      await page.waitForTimeout(2000);
      const t = await page.locator("main").innerText();
      if (/已完成/.test(t) && !/生成中|推理中|排队中|准备中|加载模型/.test(t)) { completed = true; break; }
      if (/任务失败|重试/.test(t)) break;
    }
    check("真实编辑任务完成", completed);
    await shot("23-result");

    // 结果区
    const resText = await page.locator("main").innerText();
    check("结果区下载按钮", /下载/.test(resText));
    check("结果区 A/B", /A\/B|对比|原始/.test(resText));

    // 13. 音色库授权流程
    await nav("音色库");
    const newVoiceBtn = page.locator("button", { hasText: /新建音色/ }).first();
    if (await newVoiceBtn.count()) {
      await newVoiceBtn.click();
      await page.waitForTimeout(400);
      const dlgText = await page.locator('[role="dialog"]').innerText();
      check("音色授权确认存在", /使用权|授权/.test(dlgText));
      await shot("24-voice-consent");
      await page.keyboard.press("Escape");
    } else {
      check("音色授权确认存在", false, "未找到新建音色按钮");
    }
  }

  check("无页面 JS 错误", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));
} catch (e) {
  check("测试执行异常", false, String(e).slice(0, 300));
  await shot("99-error");
} finally {
  await browser.close();
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 通过`);
fs.writeFileSync(path.join(SHOTS, "results.json"), JSON.stringify({ passed, total: results.length, results }, null, 2));
process.exit(passed === results.length ? 0 : 1);