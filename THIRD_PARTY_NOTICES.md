# Third-Party Notices

AuK Studio's own source code is licensed under the MIT License (see [LICENSE](LICENSE)).
This file lists third-party components, their licenses, and required attributions.
Model checkpoints and weights are **not** distributed with this repository; they are
downloaded by the user from official sources under their own licenses.

Dependency scan details (actual installed versions, 2026-11-14):
[docs/DEPENDENCIES_LICENSES.md](docs/DEPENDENCIES_LICENSES.md).
Model license review: [docs/MODEL_LICENSES.md](docs/MODEL_LICENSES.md).

---

## 1. Upstream: AuK (Tencent)

| Item | Value |
| --- | --- |
| Project | AuK: An Open-Source Foundational Model for Speech Generation and Editing |
| Copyright | Copyright (c) Tencent |
| License | **MIT** (covers training code, inference code, parameters and weights publicly released by Tencent) |
| Source | https://github.com/Tencent-Hunyuan/AuK |
| Branch / revision used | `feat/mlx-apple-silicon` @ `6943a1e967409e8c73139a7a345f2a611cfb3dd6` |
| License text | https://github.com/Tencent-Hunyuan/AuK/blob/main/LICENSE |
| Model cards | https://huggingface.co/tencent/AuK-Flash · https://huggingface.co/tencent/AuK |

**Integration method:** AuK Studio installs the upstream repository as a local
editable package (`uv pip install -e "./AuK[mlx]"`) and calls its `auk_mlx`
Python API / CLI. **No upstream source files are copied into this repository.**
The upstream clone is fetched by `scripts/setup.sh` and is git-ignored. If any
upstream file is ever copied or modified, the Tencent MIT copyright and license
notice must be retained and the modification documented here.

The MIT license of AuK does **not** extend to the third-party Qwen encoder that
AuK's inference chain requires (see §2).

## 2. Qwen2.5-Omni-3B (Alibaba Cloud) — required encoder, NON-COMMERCIAL

| Item | Value |
| --- | --- |
| Role | Thinker semantic encoder required by AuK inference (converted weights are derivative works, equally bound) |
| License | **Qwen RESEARCH LICENSE AGREEMENT** (Release 2024-09-19) |
| Model card | https://huggingface.co/Qwen/Qwen2.5-Omni-3B |
| Full license | https://huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/main/LICENSE |
| Distribution | **Not included in this repository or any release artifact.** Users download it themselves via `scripts/download_models.sh` (ModelScope / HuggingFace official sources). |

Required attribution (per license §3):

> Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT,
> Copyright (c) Alibaba Cloud. All Rights Reserved.

Key terms (summary only — the full license text governs):

- §1.i / §2.a: licensed for **Non-Commercial purposes only**, where
  "Non-Commercial shall mean for research or evaluation purposes only".
- §2.b: "If you are commercially using the Materials, you shall request a
  license from us" — commercial use requires a separate license from Alibaba Cloud.
- §3: redistribution must include a copy of the license, prominent notices on
  modified files, and the Notice attribution above.
- §4.b: if you use the materials' outputs to train/improve and distribute AI
  models, product documentation must prominently state "Built with Qwen" /
  "Improved using Qwen".
- §4.a: export-control compliance; §5.b: no trademark license granted.

**Consequences for this project:**

- The combination "MIT AuK weights + Research-only Qwen encoder" means the
  **complete inference system is restricted to non-commercial research /
  evaluation / personal use** until a commercial Qwen license is obtained.
- Making users download the weights themselves does not remove these use
  restrictions, and this project's MIT license does not grant any commercial
  rights to the Qwen materials.
- See upstream discussion: https://github.com/Tencent-Hunyuan/AuK/issues/13

## 3. Python runtime components

Licenses verified against the actual installed environment (pip-licenses scan,
2026-11-14). Full table: [docs/DEPENDENCIES_LICENSES.md §2](docs/DEPENDENCIES_LICENSES.md).

### MIT

| Component | Copyright / source |
| --- | --- |
| FastAPI | Sebastián Ramírez and contributors — https://github.com/fastapi/fastapi |
| Pydantic / pydantic-core | Samuel Colvin and contributors — https://github.com/pydantic/pydantic |
| **MLX / mlx-metal** | **Apple Inc. — https://github.com/ml-explore/mlx** (MIT, not Apache-2.0) |
| einops / einx / x-transformers / torch-einops-utils / torchdiffeq | respective authors (see scan) |
| loguru, PyYAML, filelock, platformdirs, watchfiles, urllib3, annotated-types, annotated-doc, anyio, exceptiongroup, h11, httptools, charset-normalizer, cffi (MIT-0), inquirerpy, pfzy, typing-inspection | respective authors |

### Apache-2.0

| Component | Source |
| --- | --- |
| transformers | Hugging Face — https://github.com/huggingface/transformers |
| safetensors | Hugging Face — https://github.com/huggingface/safetensors |
| huggingface-hub / hf-xet | Hugging Face |
| tokenizers | Hugging Face |
| qwen-omni-utils | Qwen team — https://github.com/QwenLM |
| python-multipart, msgpack, opentelemetry-api (API only; no telemetry is collected), requests, regex (AND CNRI-Python), packaging (OR BSD-2), uvloop (OR MIT) | respective authors |

Apache-2.0 components: license text at https://www.apache.org/licenses/LICENSE-2.0 ;
NOTICE files of each package are retained in their installed distributions.

### BSD-style

| Component | License | Source |
| --- | --- | --- |
| PyTorch / torchaudio / torchvision | BSD-3-Clause (torch: BSD-style) | https://github.com/pytorch — used for weight conversion and HF processor only; MLX inference does not use torch |
| NumPy / SciPy / scikit-learn | BSD-3-Clause | respective projects |
| soundfile (Python wrapper) | BSD-3-Clause | https://github.com/bastibe/python-soundfile |
| uvicorn / Starlette | BSD-3-Clause | Encode / respective authors |
| Jinja2 / MarkupSafe / click | BSD-3-Clause | Pallets |
| python-dotenv | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| librosa | ISC | https://librosa.org |
| numba | BSD-2-Clause | https://numba.pydata.org |
| llvmlite | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | https://github.com/numba/llvmlite |
| pillow | MIT-CMU (HPND) | https://python-pillow.github.io |
| typing-extensions | PSF-2.0 | https://github.com/python/typing_extensions |

### LGPL / MPL (copyleft, used unmodified via dynamic linking / import)

| Component | License | Notes |
| --- | --- | --- |
| **soxr** (python-soxr, bundles libsoxr) | **LGPL-2.1-or-later** | https://github.com/dofuuz/python-soxr — audio resampling; imported, not modified; users may replace it via pip |
| **libsndfile** (bundled with soundfile) | **LGPL-2.1** | COPYING shipped in `soundfile/_soundfile_data/`; https://libsndfile.github.io/libsndfile/ |
| **frozendict** | **LGPL-3.0-only** | https://github.com/Marco-Sulla/python-frozendict — pure-Python dependency of einx; imported, not modified |
| **certifi** | **MPL-2.0** | https://github.com/certifi/python-certifi — CA bundle used as data, unmodified |
| tqdm | MPL-2.0 AND MIT | used under the **MIT** option; https://github.com/tqdm/tqdm |

LGPL compliance: these libraries are installed by the user through pip/uv, are
not modified, and remain replaceable. No binary bundling is performed by this
project. If that changes, re-review LGPL obligations (relinkability, license
copies) before release.

## 4. Frontend components

### Bundled into the web UI (production dependencies)

| Component | Version | License | Source |
| --- | --- | --- | --- |
| React / react-dom | 18.3.1 | MIT | Meta Platforms, Inc. and affiliates — https://github.com/facebook/react |
| scheduler / loose-envify / js-tokens / csstype | — | MIT | respective authors |
| **WaveSurfer.js** | 7.12.12 | **BSD-3-Clause** | https://github.com/katspaugh/wavesurfer.js |
| **lucide-react** (icons) | 1.73.0 | **ISC** | Lucide Contributors — https://github.com/lucide-icons/lucide |

### Build-time only (not distributed)

| Component | License |
| --- | --- |
| Vite / @vitejs/plugin-react / esbuild / Rollup / PostCSS / Babel | MIT |
| Tailwind CSS / @tailwindcss/* | MIT — https://github.com/tailwindlabs/tailwindcss |
| TypeScript | Apache-2.0 |
| lightningcss | MPL-2.0 (build-time CSS minifier; not shipped) |
| caniuse-lite | CC-BY-4.0 (browser data, build-time only; not shipped) |
| Playwright (UI tests) | Apache-2.0 |

## 5. FFmpeg (system binary, not distributed)

AuK Studio invokes the user's locally installed `ffmpeg` executable as a
subprocess for audio decoding fallback. **No FFmpeg code or binary is linked,
bundled, or distributed by this project.** FFmpeg is licensed LGPL-2.1-or-later
or GPL-2.0-or-later (GPL-3.0-or-later with `--enable-version3`) depending on
build options; the reference machine's Homebrew build is GPL
(`--enable-gpl --enable-version3 --enable-libx264 --enable-libx265`).
Users obtain FFmpeg under their own channel's terms. https://ffmpeg.org/

## 6. Development-only components (never shipped)

The offline ASR verification toolchain (funasr, MIT) pulls in **kaldiio**,
whose installed 2.18.1 distribution carries the **NTT SOFTWARE LICENSE
AGREEMENT FOR EVALUATION** — evaluation-only, **no redistribution**. It is
absent from the runtime lock file and must never be included in any release
artifact. See [docs/DEPENDENCIES_LICENSES.md §4.1](docs/DEPENDENCIES_LICENSES.md).
Other dev-only packages (modelscope Apache-2.0, pip-licenses MIT, etc.) are
listed in the same document.

## 7. Trademarks

AuK is a model name published by Tencent; Qwen is a trademark of Alibaba Cloud.
AuK Studio is an independent, unofficial community project and is not
affiliated with or endorsed by Tencent or Alibaba Cloud. No rights to these
names or logos are granted by this repository's license. "AuK Studio" is a
working name pending trademark clearance.