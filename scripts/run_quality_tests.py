#!/usr/bin/env python3
"""通过 Web API 运行固定中文测试集（方案 §10 质量验收）。

对每段测试音频执行 词 / 短语 / 整句 三种替换，收集耗时、RTF、峰值内存、
失败率，下载候选音频，并生成主观评分表供用户 A/B 试听打分。

用法：.venv-auk/bin/python scripts/run_quality_tests.py [--base-url http://127.0.0.1:7860]
前置：服务已启动（./scripts/start.sh），测试集已生成（scripts/make_test_set.py）。
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 实测结论：保持类指令过多会导致模型忽略编辑（见 TEST_REPORT.md），默认仅保留音色+情绪
STYLE = "尽可能保持原音色和原始情绪。"


def req(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read())


def upload(base: str, wav: Path) -> dict:
    boundary = "----auktestboundary"
    content = wav.read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{wav.name}\"\r\n"
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    r = urllib.request.Request(base + "/api/audio/upload", data=body, method="POST",
                               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:7860")
    ap.add_argument("--bits", type=int, default=8)
    ap.add_argument("--model", choices=["flash", "base"], default="flash")
    ap.add_argument("--nfe", type=int, default=32)
    ap.add_argument("--out", default=None, help="结果子目录名（默认 test-results-<model>）")
    args = ap.parse_args()
    base = args.base_url

    manifest = json.loads((ROOT / "data" / "test-set" / "manifest.json").read_text())
    out_dir = ROOT / "data" / (args.out or f"test-results-{args.model}")
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    print(f"提交测试任务：{len(manifest)} 段 × 3 种替换 = {len(manifest)*3} 个任务（串行）")
    for case in manifest:
        wav = ROOT / case["wav"]
        aud = upload(base, wav)
        for kind, (orig, rep) in case["edits"].items():
            body = {
                "audio_id": aud["id"],
                "original_text": case["transcript"],
                "instruction": STYLE, "bits": args.bits, "seed": 42,
                "model_variant": args.model,
                "nfe": args.nfe if args.model == "base" else None,
            }
            if kind == "sentence":
                # 整句替换走全文模式（零样本 TTS 模板，实测跟随更好）
                body.update(mode="full", target_text=rep)
            else:
                body.update(mode="replace", segment={"original": orig, "replacement": rep})
            j = req(base, "POST", "/api/jobs", body)
            jobs.append({"case": case["id"], "kind": kind, "job_id": j["id"],
                         "orig": orig, "rep": rep, "input_duration": aud["duration"]})
    print(f"已提交 {len(jobs)} 个任务，等待完成…")

    pending = {j["job_id"]: j for j in jobs}
    t0 = time.time()
    first_load = None
    while pending:
        time.sleep(3)
        for jid in list(pending):
            j = req(base, "GET", f"/api/jobs/{jid}")
            if j["status"] in ("completed", "failed", "cancelled"):
                rec = pending.pop(jid)
                rec.update(status=j["status"], elapsed_s=j["elapsed_s"], rtf=j["rtf"],
                           peak_memory_gb=j["peak_memory_gb"], output_duration=j["output_duration"],
                           error=j["error"])
                if j["status"] == "completed" and j["output_path"]:
                    dst = out_dir / f"{rec['case']}-{rec['kind']}.wav"
                    urllib.request.urlretrieve(base + f"/api/files/{[f['id'] for f in req(base,'GET',f'/api/jobs/{jid}')['files'] if f['kind']=='candidate'][0]}", dst)
                    rec["output_wav"] = str(dst.relative_to(ROOT))
                if first_load is None and j.get("elapsed_s"):
                    first_load = j["elapsed_s"]
                print(f"  [{len(jobs)-len(pending)}/{len(jobs)}] {rec['case']}-{rec['kind']}: "
                      f"{j['status']} ({j['elapsed_s']:.1f}s)" if j['elapsed_s'] else f"  {rec['case']}-{rec['kind']}: {j['status']}")
        if time.time() - t0 > 3600:
            print("超时 1 小时，停止等待")
            break

    done = [j for j in jobs if j.get("status") == "completed"]
    failed = [j for j in jobs if j.get("status") == "failed"]
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": args.model, "nfe": args.nfe if args.model == "base" else 4,
        "style_instruction": STYLE,
        "bits": args.bits,
        "total": len(jobs), "completed": len(done), "failed": len(failed),
        "pending": len(pending),
        "failure_rate": len(failed) / len(jobs) if jobs else 0,
        "avg_elapsed_s": sum(j["elapsed_s"] for j in done) / len(done) if done else None,
        "avg_rtf": sum(j["rtf"] for j in done if j["rtf"]) / len(done) if done else None,
        "max_peak_memory_gb": max((j["peak_memory_gb"] or 0) for j in done) if done else None,
        "jobs": jobs,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    # 主观评分表
    lines = ["# 中文测试集主观评分表", "",
             f"生成时间：{summary['timestamp']} · 精度：{args.bits}-bit · 完成 {len(done)}/{len(jobs)}",
             "", "评分维度（权重）：音色一致性 30 / 情绪一致性 25 / 韵律与语速 20 / 拼接自然度 15 / 文字准确性 10",
             "每项 1–5 分。请在工作台 A/B 对比试听后填写。", "",
             "| 用例 | 替换类型 | 原文 → 新文 | 音色(30) | 情绪(25) | 韵律(20) | 拼接(15) | 文字(10) | 加权总分 | 备注 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for j in jobs:
        lines.append(f"| {j['case']} | {j['kind']} | {j['orig']} → {j['rep']} | | | | | | | |")
    (out_dir / "SCORESHEET.md").write_text("\n".join(lines))

    print(f"\n=== 汇总 ===")
    print(f"完成 {len(done)}/{len(jobs)}，失败 {len(failed)}，失败率 {summary['failure_rate']:.1%}")
    print(f"平均耗时 {summary['avg_elapsed_s']:.1f}s，平均 RTF {summary['avg_rtf']:.2f}" if done else "无完成任务")
    print(f"最大峰值内存 {summary['max_peak_memory_gb']} GB")
    print(f"结果: {out_dir / 'summary.json'}")
    print(f"评分表: {out_dir / 'SCORESHEET.md'}")


if __name__ == "__main__":
    main()