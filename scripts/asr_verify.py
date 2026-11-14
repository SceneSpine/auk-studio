#!/usr/bin/env python3
"""对质量测试输出做 ASR 客观验证（文字准确性 + 情绪检测）。

用法：MODELSCOPE_CACHE=$PWD/models/asr .venv-auk/bin/python scripts/asr_verify.py
输入：data/test-results/summary.json + 各候选 wav
输出：data/test-results/asr_verification.json
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MODELSCOPE_CACHE", str(ROOT / "models" / "asr"))

import sys
RESULTS = ROOT / "data" / (sys.argv[1] if len(sys.argv) > 1 else "test-results")


def normalize(t: str) -> str:
    t = re.sub(r"<\|[^|]*\|>", "", t)
    t = re.sub(r"[，。！？、,.!?\s…·：:；;\"'‘’“”]", "", t)
    # 同音字归一：他/她/它 普通话同音，ASR 无法区分
    t = t.replace("她", "他").replace("它", "他")
    return t.lower()


def main() -> None:
    from funasr import AutoModel

    summary = json.loads((RESULTS / "summary.json").read_text())
    model = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, device="cpu", disable_update=True)

    records = []
    n_pass = 0
    for j in summary["jobs"]:
        if j.get("status") != "completed" or not j.get("output_wav"):
            continue
        wav = ROOT / j["output_wav"]
        if not wav.exists():
            continue
        r = model.generate(input=str(wav), language="zh", use_itn=False)[0]["text"]
        emo_m = re.search(r"<\|(NEUTRAL|HAPPY|ANGRY|SAD|FEARFUL|DISGUSTED|SURPRISED)\|>", r)
        emo = emo_m.group(1) if emo_m else "?"
        text = normalize(r)
        rep = normalize(j["rep"])
        orig = normalize(j["orig"])
        has_rep = rep in text
        # 整句替换时原句应消失；词/短语替换时原片段应消失（可能被包含在新片段中则跳过）
        orig_gone = (orig not in text) if orig not in rep else True
        ok = has_rep and orig_gone
        n_pass += int(ok)
        records.append({
            "case": j["case"], "kind": j["kind"], "job_id": j["job_id"],
            "asr_text": re.sub(r"<\|[^|]*\|>", "", r), "emotion": emo,
            "expected_replacement": j["rep"],
            "replacement_present": has_rep, "original_removed": orig_gone, "pass": ok,
        })
        print(f"  {j['case']}-{j['kind']}: {'✓' if ok else '✗'} [{emo}] {records[-1]['asr_text'][:50]}")

    out = {"total": len(records), "pass": n_pass,
           "text_accuracy": n_pass / len(records) if records else 0, "records": records}
    (RESULTS / "asr_verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n文字准确性: {n_pass}/{len(records)} = {out['text_accuracy']:.1%}")


if __name__ == "__main__":
    main()