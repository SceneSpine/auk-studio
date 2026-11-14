#!/usr/bin/env python3
"""能力门禁实测（方案 03 §1 / Sprint 0）。

1. 基线：通过运行中的 Web API 跑一条真实局部替换任务，记录到 data/capability-tests/baseline.json。
2. 逐项实测 MLX 未验证能力：instruct_tts（无参考）、emotion_edit、timbre_edit。
   每项先用主模板，失败则试备选模板；ASR（SenseVoiceSmall）客观验证文字/情绪。
3. 输出 config/capabilities.json（后端 /api/capabilities 读取）+ data/capability-tests/report.json。

用法：.venv-auk/bin/python scripts/verify_capabilities.py [--skip-baseline]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_CACHE", str(ROOT / "models" / "asr"))
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "capability-tests"
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / "data" / "test-set" / "01-normal.wav"
SRC_TRANSCRIPT = "明天上午十点，我们在三楼会议室开会，请准时参加。"


def norm(t: str) -> str:
    t = re.sub(r"<\|[^|]*\|>", "", t)
    t = re.sub(r"[，。！？、,.!?\s…·：:；;\"'‘’“”]", "", t)
    return t.replace("她", "他").replace("它", "他").lower()


def baseline_via_api() -> dict:
    """通过运行中的服务跑一条真实编辑任务（旧代码基线）。"""
    import uuid

    port = json.loads((ROOT / "data" / "runtime.json").read_text())["port"]
    base = f"http://127.0.0.1:{port}"
    boundary = uuid.uuid4().hex
    data = SRC.read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"01-normal.wav\"\r\n"
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        base + "/api/audio/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    aud = json.loads(urllib.request.urlopen(req, timeout=120).read())
    t0 = time.time()
    req = urllib.request.Request(
        base + "/api/jobs",
        data=json.dumps({
            "audio_id": aud["id"], "mode": "replace",
            "segment": {"original": "会议室", "replacement": "发布会"},
            "instruction": "尽可能保持原音色和原始情绪。",
            "model_variant": "flash", "bits": 8, "seed": 42,
        }).encode(), headers={"Content-Type": "application/json"})
    job = json.loads(urllib.request.urlopen(req, timeout=30).read())
    jid = job["id"]
    while time.time() - t0 < 300:
        j = json.loads(urllib.request.urlopen(base + f"/api/jobs/{jid}", timeout=30).read())
        if j["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(1)
    return {
        "job_id": jid, "status": j["status"], "elapsed_s": j.get("elapsed_s"),
        "rtf": j.get("rtf"), "peak_memory_gb": j.get("peak_memory_gb"),
        "output_duration": j.get("output_duration"), "error": j.get("error", ""),
        "final_instruction": j.get("final_instruction", ""),
        "wall_s": round(time.time() - t0, 1), "at": time.time(),
    }


def main() -> None:
    skip_baseline = "--skip-baseline" in sys.argv
    report: dict = {"device": "M5 Pro / 48GB", "at": time.time(), "tests": []}

    if not skip_baseline:
        print("== 基线：Web API 真实编辑任务 ==", flush=True)
        try:
            report["baseline"] = baseline_via_api()
            print(json.dumps(report["baseline"], ensure_ascii=False, indent=2), flush=True)
        except Exception as e:  # noqa: BLE001
            report["baseline"] = {"error": str(e)}
            print("基线失败:", e, flush=True)
        (OUT / "baseline.json").write_text(json.dumps(report["baseline"], ensure_ascii=False, indent=2))

    print("== 加载引擎（flash / 8-bit）==", flush=True)
    from app.backend import config
    from auk_mlx.infer import AukMLX, GenerateOptions

    t0 = time.time()
    engine = AukMLX(
        str(config.MLX_DIR), str(config.FLASH_DIR / "config.yaml"), str(config.QWEN_DIR),
        bits=8, group_size=64, sequential=False)
    print(f"引擎加载 {time.time() - t0:.1f}s", flush=True)

    def gen(name: str, instruction: str, audio: str | None, gen_seconds: float | None) -> dict:
        t = time.time()
        wav, sr = engine.generate(instruction, audio_path=audio,
                                  opts=GenerateOptions(gen_seconds=gen_seconds, seed=42))
        import soundfile as sf
        out = OUT / f"{name}.wav"
        sf.write(str(out), wav, sr, subtype="PCM_16")
        rec = {"name": name, "instruction": instruction, "audio": audio,
               "gen_seconds": gen_seconds, "wall_s": round(time.time() - t, 1),
               "duration": round(len(wav) / sr, 2), "wav": str(out.relative_to(ROOT))}
        print(f"  {name}: {rec['wall_s']}s -> {rec['duration']}s", flush=True)
        return rec

    # --- instruct_tts：无参考音频，描述 + 文本 ---
    desc = "一位二十多岁的女性，语气活泼开朗，语速稍快，音色清亮自然。"
    text = "大家好，欢迎来到今天的节目，我们一起聊聊最近发生的新鲜事。"
    est = len(text) / 4.0 + 0.5
    report["tests"].append(gen("instruct_tts",
        f'Based on the following description: "{desc}", generate speech content "{text}".',
        None, est))

    # --- emotion_edit：中性源 -> 开心 ---
    report["tests"].append(gen("emotion_en", "Change the emotion to happy.", str(SRC), None))
    report["tests"].append(gen("emotion_cn", "将情感转变为开心。", str(SRC), None))

    # --- timbre_edit：内容不变，音色改为描述 ---
    tdesc = "低沉平静的女性声音"
    report["tests"].append(gen("timbre_cn",
        f'请将这段音频的音色修改为符合以下描述的声音：“{tdesc}”。', str(SRC), None))
    report["tests"].append(gen("timbre_en",
        f'Keep the spoken content unchanged and change the timbre to: "a deep, calm female voice".',
        str(SRC), None))

    # --- ASR 客观验证 ---
    print("== ASR 验证（SenseVoiceSmall, CPU）==", flush=True)
    from funasr import AutoModel
    asr = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, device="cpu", disable_update=True)
    for rec in report["tests"]:
        r = asr.generate(input=str(ROOT / rec["wav"]), language="zh", use_itn=False)[0]["text"]
        emo = re.search(r"<\|(NEUTRAL|HAPPY|ANGRY|SAD|FEARFUL|DISGUSTED|SURPRISED)\|>", r)
        rec["asr_text"] = re.sub(r"<\|[^|]*\|>", "", r)
        rec["asr_emotion"] = emo.group(1) if emo else "?"
        print(f"  {rec['name']}: [{rec['asr_emotion']}] {rec['asr_text']}", flush=True)

    # --- 判定 ---
    def find(n):
        return next(t for t in report["tests"] if t["name"] == n)

    it = find("instruct_tts")
    it["pass"] = norm(text) in norm(it["asr_text"])
    emo_best = max([find("emotion_en"), find("emotion_cn")],
                   key=lambda r: (r["asr_emotion"] == "HAPPY", norm(SRC_TRANSCRIPT) in norm(r["asr_text"])))
    tim_best = max([find("timbre_cn"), find("timbre_en")],
                   key=lambda r: norm(SRC_TRANSCRIPT) in norm(r["asr_text"]))
    for rec in report["tests"]:
        if rec["name"].startswith("emotion"):
            rec["pass"] = rec is emo_best and rec["asr_emotion"] == "HAPPY" and norm(SRC_TRANSCRIPT) in norm(rec["asr_text"])
        elif rec["name"].startswith("timbre"):
            rec["pass"] = rec is tim_best and norm(SRC_TRANSCRIPT) in norm(rec["asr_text"])

    now = time.time()
    caps = {
        "backend": "mlx",
        "verified_at": now,
        "tasks": {
            "speech_edit": {"state": "supported", "models": ["flash", "base"],
                            "note": "本机 30 例回归 Flash 86.7% / Base 76.7%（docs/TEST_REPORT.md）",
                            "verified_at": now},
            "zero_shot_tts": {"state": "supported", "models": ["flash", "base"],
                              "note": "全文替换模式即零样本 TTS 英文模板，整句 10/10（docs/TEST_REPORT.md §3.3）",
                              "verified_at": now},
            "instruction_tts": {
                "state": "supported" if it["pass"] else "unverified",
                "models": ["flash", "base"] if it["pass"] else [],
                "note": f"无参考描述式 TTS 实测{'通过' if it['pass'] else '未通过'}：ASR={it['asr_text'][:60]}",
                "verified_at": now},
            "emotion_edit": {
                "state": "supported" if emo_best["pass"] else "unverified",
                "models": ["flash", "base"] if emo_best["pass"] else [],
                "note": f"情绪编辑实测{'通过' if emo_best['pass'] else '未通过'}（{emo_best['name']}，ASR 情绪={emo_best['asr_emotion']}）",
                "verified_at": now},
            "timbre_edit": {
                "state": "supported" if tim_best["pass"] else "unverified",
                "models": ["flash", "base"] if tim_best["pass"] else [],
                "note": f"音色重塑实测{'通过' if tim_best['pass'] else '未通过'}（{tim_best['name']}，内容保持={norm(SRC_TRANSCRIPT) in norm(tim_best['asr_text'])}）",
                "verified_at": now},
            "speech_enhancement": {"state": "not_supported", "models": [],
                                   "note": "MLX 分支未实现降噪/去混响；官方 CUDA 路径能力不代表 MLX 可用", "verified_at": now},
            "source_separation": {"state": "not_supported", "models": [],
                                  "note": "MLX 分支未实现说话人/源分离", "verified_at": now},
            "asr_alignment": {"state": "not_supported", "models": [],
                              "note": "未集成 ASR/强制对齐到工作台（离线验证脚本除外）", "verified_at": now},
        },
        "preferred_templates": {
            "emotion": emo_best["instruction"] if emo_best["pass"] else "Change the emotion to happy.",
            "timbre": tim_best["instruction"] if tim_best["pass"] else 'Keep the spoken content unchanged and change the timbre to: "{description}".',
        },
    }
    (ROOT / "config" / "capabilities.json").write_text(json.dumps(caps, ensure_ascii=False, indent=2))
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("== 完成 ==", flush=True)
    print(json.dumps({k: v["state"] for k, v in caps["tasks"].items()}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()