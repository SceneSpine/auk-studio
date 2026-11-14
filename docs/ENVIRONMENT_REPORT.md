# 本机环境报告（ENVIRONMENT_REPORT）

> 检查时间：2026-11-14（本机实际执行，非推断）
> 项目根目录：`<项目根目录>`
> 说明：方案建议目录为 `~/AI-Audio-Lab/`，实际采用当前工作目录 `<项目根目录>`（已存在且包含方案文档），结构一致。

## 硬件

| 项目 | 实测值 |
| --- | --- |
| 机型 | MacBook Pro（Mac17,9） |
| 芯片 | Apple M5 Pro |
| CPU | 18 核（6 Super + 12 Performance），arm64 |
| GPU | 20 核，Metal 4 支持 |
| 统一内存 | 48 GB（hw.memsize = 51539607552） |
| 显示器 | 3024 × 1964 Liquid Retina XDR |

## 系统

| 项目 | 实测值 |
| --- | --- |
| macOS | 26.5.1（Build 25F80） |
| 架构 | arm64（`uname -m`） |
| 磁盘 | 926 GB 总容量，**536 GB 可用**（`df -h /`） |
| 内存压力 | 检查时系统有历史 swap 记录（swapins 2.6M / swapouts 4.2M 页），空闲页偏少；部署与推理期间需持续观察 `memory_pressure` |

磁盘预算：原始权重约 18.8 GB + fp32 转换约 21.7 GB + 8-bit 量化副本约 6.6 GB ≈ **47 GB**，另加输出/日志余量。536 GB 可用，满足方案 ≥60 GB 预算要求。

## 工具链

| 工具 | 路径 | 版本 |
| --- | --- | --- |
| Homebrew | /opt/homebrew/bin/brew | 7.0.13 |
| Git | /usr/bin/git | 2.50.1 (Apple Git-155) |
| uv | /opt/homebrew/bin/uv | 0.13.8 |
| FFmpeg | /opt/homebrew/bin/ffmpeg | 9.0.2 |
| 系统 Python | /usr/bin/python3 | 3.9.6（仅系统自带，不用于本项目） |
| Node.js | /opt/homebrew/bin/node | v22.23.2 |
| npm | /opt/homebrew/bin/npm | 10.9.8 |

## 网络

- `github.com` git 直连不稳定（HTTP2 framing error / 连接超时）；**git 需走 SOCKS 代理 `<你的 SOCKS 代理>`**（按需自设）。
- `huggingface.co` API/下载直连失败，需走同一代理；备选官方渠道 ModelScope（README 列出的官方分发）。
- `pypi.org` 直连可用。
- 克隆方式：`git -c http.proxy=<你的代理> clone --depth 1 --branch feat/mlx-apple-silicon ...`（完整克隆曾中断，浅克隆成功）。

## MLX 兼容性判断

- 官方 MLX 后端验证环境：M4 Pro 48GB / macOS 26.4 / Python 3.10 / mlx 0.32.2（docs/MLX.md）。
- 本机 M5 Pro / macOS 26.5.1 更新，mlx 最新 0.32.4（PyPI，requires_python >=3.10）。
- **不预设结论**：安装后按方案 §4.2 执行最小 MLX/Metal 测试，以实测为准。

## 环境隔离

- 本项目使用独立虚拟环境 `.venv-auk/`（uv 管理，Python 3.10，官方 `.python-version` 指定）。
- 不触碰系统 Python、SceneSpine-Studio 或其他项目环境。
- 模型、音频、日志全部位于本项目 `models/`、`data/`、`logs/`，默认不上传第三方。