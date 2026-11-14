"""worker 指令模板（严格按 docs/CAPABILITIES.md）与 install/verify 执行逻辑。

不加载模型、不触网：install/verify 用微型 registry + 本地小文件。
"""
from __future__ import annotations

import pytest

from app.backend import model_manager, worker


# ---------------- build_instruction ----------------

def test_replace_template():
    job = {"mode": "replace", "segment": {"original": "会议室", "replacement": "发布会"},
           "instruction": "尽可能保持原音色和原始情绪。"}
    assert worker.build_instruction(job) == "把‘会议室’改成‘发布会’。 尽可能保持原音色和原始情绪。"


def test_full_english_tts_template_no_extra():
    job = {"mode": "full", "target_text": "今天天气真好", "instruction": "尽可能保持原音色。"}
    assert worker.build_instruction(job) == "Say the following with the same voice: '今天天气真好'"


def test_tts_same_as_full():
    job = {"mode": "tts", "target_text": "你好世界", "instruction": "保持情绪"}
    assert worker.build_instruction(job) == "Say the following with the same voice: '你好世界'"


def test_instruct_tts_template():
    job = {"mode": "instruct_tts", "description": "一位二十多岁的女性，语气活泼开朗。",
           "target_text": "今天天气真好，我们出去走走吧。"}
    assert worker.build_instruction(job) == (
        'Based on the following description: "一位二十多岁的女性，语气活泼开朗。", '
        'generate speech content "今天天气真好，我们出去走走吧。".'
    )


def test_timbre_chinese_template():
    job = {"mode": "timbre", "description": "低沉沙哑的男声"}
    assert worker.build_instruction(job) == "请将这段音频的音色修改为符合以下描述的声音：“低沉沙哑的男声”。"


def test_emotion_chinese_template():
    job = {"mode": "emotion", "emotion": "开心"}
    assert worker.build_instruction(job) == "将情感转变为开心。"


def test_custom_uses_instruction():
    assert worker.build_instruction({"mode": "custom", "instruction": "放慢语速"}) == "放慢语速"


@pytest.mark.parametrize("job", [
    {"mode": "full", "target_text": ""},
    {"mode": "instruct_tts", "description": "", "target_text": "x"},
    {"mode": "timbre", "description": ""},
    {"mode": "emotion", "emotion": ""},
    {"mode": "replace", "segment": {}},
])
def test_missing_fields_raise(job):
    with pytest.raises(ValueError):
        worker.build_instruction(job)


# ---------------- install / verify 执行 ----------------

class _Ctx:
    def __init__(self):
        self.logs = []
        self.progresses = []

    def log(self, msg):
        self.logs.append(str(msg))

    def stage(self, status, detail):
        self.logs.append(f"[{status}] {detail}")

    def progress(self, phase, dl, tot, fd, ft, detail):
        self.progresses.append((phase, detail))

    def cancelled(self):
        return False


def test_verify_ok(tiny_model_env):
    job = {"id": "job_test_verify", "model_id": "tiny"}
    ctx = _Ctx()
    model_manager.run_verify(job, ctx)
    assert any("全部文件校验通过" in m for m in ctx.logs)


def test_verify_mismatch_fails(tiny_model_env):
    (tiny_model_env["raw"] / "a.bin").write_bytes(b"corrupted")
    job = {"id": "job_test_verify_bad", "model_id": "tiny"}
    with pytest.raises(RuntimeError, match="校验未通过"):
        model_manager.run_verify(job, _Ctx())


def test_install_all_reuse_no_network(tiny_model_env):
    """文件齐全 → download/convert 全部复用，不触网、不跑 subprocess。"""
    job = {"id": "job_test_install", "model_id": "tiny"}
    ctx = _Ctx()
    model_manager.run_install(job, ctx)
    assert any("复用已存在文件" in m for m in ctx.logs)
    assert any("安装完成" in m for m in ctx.logs)
    assert ctx.progresses[-1][0] == "done"


def test_install_cancelled_preserves_resume(tiny_model_env):
    (tiny_model_env["raw"] / "a.bin").unlink()  # 制造缺失 → 需要下载

    class _CancelCtx(_Ctx):
        def cancelled(self):
            return True

    with pytest.raises(model_manager.Cancelled):
        model_manager.run_install({"id": "job_cancel", "model_id": "tiny"}, _CancelCtx())


def test_model_job_wrapper_lifecycle(client, tiny_model_env):
    """_run_model_job：completed / failed / cancelled 状态机与 install_json 持久化。"""
    from app.backend import db

    job = db.insert_job({"audio_id": None, "mode": "verify", "kind": "verify", "model_id": "tiny"})
    worker._run_model_job(db.get_job(job["id"]), model_manager.run_verify)
    j = db.get_job(job["id"])
    assert j["status"] == "completed"
    assert j["install_json"]["phase"] == "done"

    (tiny_model_env["raw"] / "a.bin").write_bytes(b"bad")
    job2 = db.insert_job({"audio_id": None, "mode": "verify", "kind": "verify", "model_id": "tiny"})
    worker._run_model_job(db.get_job(job2["id"]), model_manager.run_verify)
    j2 = db.get_job(job2["id"])
    assert j2["status"] == "failed"
    assert "校验未通过" in j2["error"]
    # 失败可重试（旧端点回归）
    assert client.post(f"/api/jobs/{job2['id']}/retry").status_code == 200
    assert db.get_job(job2["id"])["status"] == "queued"
    client.post(f"/api/jobs/{job2['id']}/cancel")


def test_download_allowlist():
    with pytest.raises(RuntimeError, match="allowlist"):
        model_manager._check_url("https://evil.example.com/x")
    model_manager._check_url("https://modelscope.cn/models/Tencent-Hunyuan/AuK-Flash/resolve/master/a")
    model_manager._check_url("https://huggingface.co/tencent/AuK-Flash/resolve/main/a")