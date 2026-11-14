#!/usr/bin/env python3
"""生成固定中文测试集（方案 §10）。

用 AuK-Flash Instruct TTS 合成 10 段不同风格的中文对白（已知逐字稿），
其中 2 段叠加噪声 / 背景音乐。测试音频为模型合成，无版权风险；
如需真人录音测试，可替换 data/test-set/ 中的 wav 并保持 manifest 一致。

用法：.venv-auk/bin/python scripts/make_test_set.py
输出：data/test-set/*.wav + data/test-set/manifest.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "AuK" / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

OUT = ROOT / "data" / "test-set"
OUT.mkdir(parents=True, exist_ok=True)

# (id, 风格描述, 文本, 目标时长, 编辑定义)
CASES = [
    ("01-normal", "一位三十多岁的男性，用平静自然的语气说话，语速适中，吐字清晰。",
     "明天上午十点，我们在三楼会议室开会，请准时参加。", 6.0,
     {"word": ("会议室", "发布会"), "phrase": ("明天上午十点", "后天下午两点"),
      "sentence": ("明天上午十点，我们在三楼会议室开会，请准时参加。", "后天下午两点，我们在二楼报告厅集合，请大家提前到场。")}),
    ("02-fast", "一位年轻男性，语速很快，语气急促兴奋，像是在催促同伴。",
     "快点快点，车马上就要开了，再晚一步我们就赶不上了！", 4.5,
     {"word": ("车", "高铁"), "phrase": ("再晚一步", "再慢一点"),
      "sentence": ("快点快点，车马上就要开了，再晚一步我们就赶不上了！", "抓紧抓紧，飞机快要起飞了，再磨蹭我们就走不成了！")}),
    ("03-slow", "一位中年女性，语速缓慢，语气压抑克制，带着疲惫感。",
     "他走了以后，这个家就再也没有一点声音了。", 6.5,
     {"word": ("家", "屋子"), "phrase": ("再也没有", "再也没有过"),
      "sentence": ("他走了以后，这个家就再也没有一点声音了。", "她离开之后，这座房子就再也没有一丝生气了。")}),
    ("04-angry", "一位中年男性，非常愤怒，音量偏大，语气强硬，带有质问感。",
     "我说过多少次了，不要动我的东西，你到底有没有在听！", 5.5,
     {"word": ("东西", "文件"), "phrase": ("多少次", "一百次"),
      "sentence": ("我说过多少次了，不要动我的东西，你到底有没有在听！", "我提醒过多少回了，别碰我的电脑，你究竟有没有记性！")}),
    ("05-sad", "一位年轻女性，悲伤哽咽，语速偏慢，声音颤抖，带有哭腔。",
     "对不起，我真的尽力了，可是我还是没能留住他。", 6.5,
     {"word": ("他", "她"), "phrase": ("真的尽力了", "已经尽力了"),
      "sentence": ("对不起，我真的尽力了，可是我还是没能留住他。", "抱歉啊，我已经拼尽全力，但最终还是没能留下她。")}),
    ("06-whisper", "一位年轻男性，用极轻的耳语说话，音量很小，语气紧张警惕。",
     "别出声，他们就在门外，我们得想办法离开这里。", 6.0,
     {"word": ("门外", "楼下"), "phrase": ("别出声", "别说话"),
      "sentence": ("别出声，他们就在门外，我们得想办法离开这里。", "小声点，那些人就在走廊，我们必须找机会逃出去。")}),
    ("07-long", "一位四十多岁的男性领导，语气沉稳鼓励，语速适中，像是在总结工作。",
     "虽然这次实验的结果不太理想，但是大家这段时间的努力我都看在眼里，接下来我们调整方案，争取在下个月拿出更好的成绩。", 13.0,
     {"word": ("实验", "试验"), "phrase": ("不太理想", "不够理想"),
      "sentence": ("虽然这次实验的结果不太理想，但是大家这段时间的努力我都看在眼里，接下来我们调整方案，争取在下个月拿出更好的成绩。",
                   "尽管这次测试的数据不算漂亮，不过各位这些日子的付出我都记在心里，后面我们优化流程，力争在下季度交出更满意的答卷。")}),
    ("08-pause", "一位年轻女性，说话带有明显停顿和思考的语气词，节奏松散自然。",
     "嗯……我想想看，这件事，或许还有别的办法。", 6.5,
     {"word": ("办法", "出路"), "phrase": ("我想想看", "让我想想"),
      "sentence": ("嗯……我想想看，这件事，或许还有别的办法。", "呃……我考虑一下，这个问题，说不定还有其他解法。")}),
    ("09-noise", None, None, 6.0, None),   # 由 01 叠加噪声
    ("10-bgm", None, None, 6.0, None),     # 由 01 叠加背景音乐
]


def synth(engine, desc: str, text: str, seconds: float, out_path: Path) -> float:
    from auk_mlx.infer import GenerateOptions

    instruction = f'请基于下面的描述: "{desc}",生成语音内容"{text}".'
    t0 = time.time()
    wav, sr = engine.generate(instruction, opts=GenerateOptions(gen_seconds=seconds, seed=42))
    sf.write(str(out_path), wav, sr, subtype="PCM_16")
    dt = time.time() - t0
    print(f"  ✓ {out_path.name} ({len(wav)/sr:.2f}s, 耗时 {dt:.1f}s)")
    return dt


def add_noise(src: Path, dst: Path, snr_db: float = 20.0) -> None:
    wav, sr = sf.read(str(src), dtype="float32")
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, len(wav)).astype(np.float32)
    sig_p = np.mean(wav ** 2) + 1e-12
    noise_p = sig_p / (10 ** (snr_db / 10))
    noise *= np.sqrt(noise_p / (np.mean(noise ** 2) + 1e-12))
    sf.write(str(dst), wav + noise, sr, subtype="PCM_16")


def add_bgm(src: Path, dst: Path) -> None:
    """叠加柔和合成和弦垫底（正弦波，无版权）。"""
    wav, sr = sf.read(str(src), dtype="float32")
    t = np.arange(len(wav)) / sr
    chord = np.zeros(len(wav), dtype=np.float32)
    for f in (220.0, 277.18, 329.63, 440.0):
        chord += 0.25 * np.sin(2 * np.pi * f * t).astype(np.float32)
    env = np.minimum(1.0, t / 0.5) * np.minimum(1.0, (len(wav) / sr - t) / 0.5)
    chord *= env * 0.06
    sf.write(str(dst), wav + chord, sr, subtype="PCM_16")


def main() -> None:
    from auk_mlx.infer import AukMLX

    mlx_dir = ROOT / "models" / "mlx-converted"
    cfg = ROOT / "models" / "auk-flash" / "config.yaml"
    qwen = ROOT / "models" / "qwen-thinker"
    print("加载引擎（8-bit）…")
    t0 = time.time()
    engine = AukMLX(str(mlx_dir), str(cfg), str(qwen), bits=8)
    print(f"加载耗时 {time.time()-t0:.1f}s")

    manifest = []
    total_gen = 0.0
    for cid, desc, text, seconds, edits in CASES:
        if desc is None:
            continue
        out = OUT / f"{cid}.wav"
        total_gen += synth(engine, desc, text, seconds, out)
        manifest.append({
            "id": cid, "wav": str(out.relative_to(ROOT)), "transcript": text,
            "style": desc, "gen_seconds": seconds, "edits": edits,
            "source": "AuK-Flash instruct TTS 合成（seed=42）",
        })

    base = OUT / "01-normal.wav"
    add_noise(base, OUT / "09-noise.wav")
    add_bgm(base, OUT / "10-bgm.wav")
    m0 = manifest[0]
    for cid, note in (("09-noise", "01 叠加白噪声 SNR≈20dB"), ("10-bgm", "01 叠加合成和弦背景")):
        manifest.append({**m0, "id": cid, "wav": f"data/test-set/{cid}.wav", "source": note})

    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\n✓ 测试集生成完成：{len(manifest)} 段，合成总耗时 {total_gen:.1f}s")
    print(f"  清单: {OUT / 'manifest.json'}")


if __name__ == "__main__":
    main()