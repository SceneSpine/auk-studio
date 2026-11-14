#!/usr/bin/env python3
"""AuK 模型下载器（仅标准库）。

- 主渠道：ModelScope 官方仓库（README 列出的官方分发，国内直连）。
- 备渠道：HuggingFace 官方（经 SOCKS 代理，环境变量 HF_PROXY 控制）。
- 完整性：以 config/model_manifest.json 中来自 HF 官方 API 的 sha256 为准。
- 断点续传：64MB 分块并行下载，.progress 记录已完成块；中断后重跑自动续传。

用法：python3 scripts/download_models.py [--workers 8] [--only flash|qwen|all]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "config", "model_manifest.json")
CHUNK = 64 * 1024 * 1024
HF_PROXY = os.environ.get("HF_PROXY", "")  # 可选：用户自设代理；留空直连

REPOS = {
    "flash": {
        "hf": "tencent/AuK-Flash",
        "ms": "Tencent-Hunyuan/AuK-Flash",
        "dst": os.path.join(ROOT, "models", "auk-flash"),
    },
    "qwen": {
        "hf": "Qwen/Qwen2.5-Omni-3B",
        "ms": "Qwen/Qwen2.5-Omni-3B",
        "dst": os.path.join(ROOT, "models", "qwen-thinker"),
    },
    "base": {
        "hf": "tencent/AuK",
        "ms": "Tencent-Hunyuan/AuK",
        "dst": os.path.join(ROOT, "models", "auk-base"),
    },
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _opener(source: str):
    if source == "hf" and HF_PROXY:
        import urllib.request as u

        proxy = u.ProxyHandler({"https": HF_PROXY, "http": HF_PROXY})
        return u.build_opener(proxy)
    return urllib.request.build_opener()


def fetch_range(url: str, start: int, end: int, source: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "auk-local-studio/1.0"})
    with _opener(source).open(req, timeout=timeout) as r:
        return r.read()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def urls_for(repo: dict, rel: str) -> dict:
    return {
        "ms": f"https://modelscope.cn/models/{repo['ms']}/resolve/master/{rel}",
        "hf": f"https://huggingface.co/{repo['hf']}/resolve/main/{rel}",
    }


def download_file(repo: dict, rel: str, meta: dict, workers: int) -> None:
    dst = os.path.join(repo["dst"], rel)
    size = meta["size"]
    expect = meta.get("sha256")
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if os.path.isfile(dst) and os.path.getsize(dst) == size:
        if not expect or sha256_file(dst) == expect:
            log(f"✓ 已存在且校验通过: {rel}")
            return
        log(f"✗ 已存在但校验失败，重新下载: {rel}")
        os.remove(dst)

    part = dst + ".part"
    prog_path = dst + ".progress"
    n_chunks = max(1, (size + CHUNK - 1) // CHUNK)
    done: set[int] = set()
    if os.path.isfile(part) and os.path.getsize(part) == size and os.path.isfile(prog_path):
        done = set(json.load(open(prog_path)))
        log(f"↻ 续传 {rel}: {len(done)}/{n_chunks} 块已完成")
    else:
        with open(part, "wb") as f:
            f.truncate(size)
        done = set()

    urls = urls_for(repo, rel)
    lock_print = __import__("threading").Lock()
    t0 = time.time()
    downloaded = [len(done) * CHUNK]

    def do_chunk(i: int) -> int:
        start = i * CHUNK
        end = min(size - 1, start + CHUNK - 1)
        last_err = None
        for attempt in range(6):
            source = "ms" if attempt < 4 else "hf"
            try:
                data = fetch_range(urls[source], start, end, source)
                if len(data) != end - start + 1:
                    raise IOError(f"short read {len(data)} != {end - start + 1}")
                with open(part, "r+b") as f:
                    f.seek(start)
                    f.write(data)
                with lock_print:
                    done.add(i)
                    downloaded[0] += len(data)
                    json.dump(sorted(done), open(prog_path, "w"))
                    el = time.time() - t0
                    spd = downloaded[0] / el / 1e6 if el > 0 else 0
                    if i % 8 == 0 or len(done) == n_chunks:
                        log(f"  {rel}: {len(done)}/{n_chunks} 块 ({spd:.1f} MB/s)")
                return i
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(min(2 ** attempt, 15))
        raise RuntimeError(f"chunk {i} of {rel} failed after retries: {last_err}")

    if size <= CHUNK or workers <= 1:
        for i in range(n_chunks):
            if i not in done:
                do_chunk(i)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(do_chunk, i) for i in range(n_chunks) if i not in done]
            for fu in as_completed(futs):
                fu.result()

    if expect:
        log(f"  校验 sha256: {rel} ...")
        actual = sha256_file(part)
        if actual != expect:
            os.remove(part)
            os.remove(prog_path)
            raise RuntimeError(f"sha256 mismatch for {rel}: {actual} != {expect}")
    os.replace(part, dst)
    if os.path.isfile(prog_path):
        os.remove(prog_path)
    log(f"✓ 完成: {rel} ({size / 1e9:.2f} GB, {time.time() - t0:.0f}s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", choices=["flash", "qwen", "base", "all"], default="all")
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST))
    targets = ["flash", "qwen"] if args.only == "all" else [args.only]
    failed = []
    for key in targets:
        repo = REPOS[key]
        files = manifest[repo["hf"]]
        log(f"=== {repo['hf']} → {repo['dst']} ({len(files)} 文件) ===")
        # 小文件先下（config/tokenizer），大文件并行
        for rel, meta in sorted(files.items(), key=lambda kv: kv[1]["size"]):
            try:
                download_file(repo, rel, meta, args.workers)
            except Exception as e:  # noqa: BLE001
                log(f"✗ 失败: {rel}: {e}")
                failed.append(rel)
    if failed:
        log(f"共 {len(failed)} 个文件失败: {failed}")
        sys.exit(1)
    log("全部模型下载并校验完成。")


if __name__ == "__main__":
    main()