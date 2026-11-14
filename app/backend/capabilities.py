"""能力门禁：读取 config/capabilities.json（scripts/verify_capabilities.py 实测生成）。

原则（docs/CAPABILITIES.md）：AuK 官方支持 ≠ MLX 分支支持；判定以本机实测为准。
- supported   → 正常入口
- unverified  → 实验性，可提交但记录 note、不承诺效果
- not_supported → 400 拒绝，不做假按钮

文件缺失时返回保守默认（speech_edit / zero_shot_tts supported，其余 unverified）。
路径可用环境变量 AUK_CAPABILITIES_FILE 覆盖（测试用）；每次请求读取，
verify_capabilities.py 更新后无需重启。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config

# mode → capabilities 任务键
TASK_BY_MODE = {
    "replace": "speech_edit",
    "full": "speech_edit",
    "custom": "speech_edit",
    "tts": "zero_shot_tts",
    "instruct_tts": "instruction_tts",
    "timbre": "timbre_edit",
    "emotion": "emotion_edit",
}

ALL_TASKS = (
    "speech_edit",
    "zero_shot_tts",
    "instruction_tts",
    "timbre_edit",
    "emotion_edit",
    "speech_enhancement",
    "source_separation",
    "asr_alignment",
)


def capabilities_path() -> Path:
    env = os.environ.get("AUK_CAPABILITIES_FILE")
    return Path(env).expanduser() if env else config.ROOT / "config" / "capabilities.json"


def default_capabilities() -> dict:
    """保守默认：仅本机旧链路已验证的两项 supported，其余 unverified（未实测）。"""
    tasks = {}
    for t in ALL_TASKS:
        supported = t in ("speech_edit", "zero_shot_tts")
        tasks[t] = {
            "state": "supported" if supported else "unverified",
            "models": ["flash", "base"] if supported else [],
            "note": (
                "保守默认（config/capabilities.json 缺失，未实测）：旧链路已验证。"
                if supported
                else "保守默认（config/capabilities.json 缺失）：未实测，不承诺效果。"
            ),
            "verified_at": 0,
        }
    return {"backend": "mlx", "verified_at": 0, "tasks": tasks, "preferred_templates": {}}


def load_capabilities() -> dict:
    try:
        data = json.loads(capabilities_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("tasks"), dict) and data["tasks"]:
            data.setdefault("backend", "mlx")
            data.setdefault("verified_at", 0)
            data.setdefault("preferred_templates", {})
            return data
    except (OSError, ValueError):
        pass
    return default_capabilities()


def task_entry(task: str) -> dict:
    caps = load_capabilities()
    entry = caps.get("tasks", {}).get(task)
    if not isinstance(entry, dict):
        return {"state": "unverified", "models": [], "note": "能力矩阵未包含该任务（未实测）。", "verified_at": 0}
    return entry


def gate_mode(mode: str) -> tuple[bool, str, dict]:
    """返回 (allowed, note, entry)。not_supported → 拒绝；unverified → 允许但带 note。"""
    task = TASK_BY_MODE.get(mode)
    if task is None:
        return False, f"未知模式 {mode}", {}
    entry = task_entry(task)
    state = entry.get("state", "unverified")
    if state == "not_supported":
        return False, entry.get("note") or "MLX 分支未实现该能力。", entry
    note = ""
    if state == "unverified":
        note = f"实验性能力（{task}，未客观验证）：{entry.get('note') or '可试用，不承诺效果。'}"
    return True, note, entry