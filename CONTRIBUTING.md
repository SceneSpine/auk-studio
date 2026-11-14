# Contributing to AuK Studio

Thanks for your interest! AuK Studio is an **unofficial, independent community
project** — not affiliated with or endorsed by Tencent or Alibaba Cloud.
Please read [docs/MODEL_LICENSES.md](docs/MODEL_LICENSES.md) before
contributing: the required Qwen2.5-Omni-3B encoder is **non-commercial
(Qwen Research License)**, and contributions must not imply otherwise.

## 1. Development environment

Requirements: Apple Silicon Mac, macOS, Homebrew, Git, uv, FFmpeg, Node.js ≥ 18.
Recommended: 48GB unified memory, ≥ 60GB free disk.

```bash
# 0. Upstream AuK must exist at ./AuK (MLX branch; not shipped with this repo)
git clone --depth 1 -b feat/mlx-apple-silicon https://github.com/Tencent-Hunyuan/AuK.git AuK

# 1. Python 3.10 venv + AuK[mlx] + backend deps
./scripts/setup.sh

# 2. Models (official ModelScope channel, sha256-verified, resumable)
./scripts/download_models.sh
./scripts/convert_models.sh          # MLX conversion + 8-bit copies

# 3. Frontend dev server (hot reload) or production build
cd app/frontend && npm install
npm run dev                          # or: npm run build

# 4. Run the workbench
./scripts/start.sh                   # http://127.0.0.1:7860
./scripts/doctor.sh                  # environment diagnostics
```

- Runtime Python deps are pinned in `config/requirements-lock.txt`.
- **Never re-download or re-convert weights that already exist** — the install
  flow must probe and reuse (see docs/BASELINE.md constraints).
- Do not commit changes to `data/` (database, uploads, outputs) — it is
  git-ignored working data.

## 2. Code style

- **Python**: follow existing backend conventions (FastAPI + Pydantic schemas,
  loguru logging, SQLite WAL). Keep the adapter layer thin — call upstream
  `auk_mlx`, do not vendor upstream source. Type-annotate public functions.
  Recommended: `ruff` for lint/format (not yet enforced in CI).
- **TypeScript/React**: strict mode (`tsc -b` must pass), function components
  + hooks, Tailwind utility classes with the design tokens in `index.css`.
  No new UI dependency without a license check (must be permissive; update
  docs/DEPENDENCIES_LICENSES.md and THIRD_PARTY_NOTICES.md).
- **Capability gating is mandatory**: UI entries must reflect
  `config/capabilities.json` (`supported` / `unverified` → experimental badge /
  `not_supported` → disabled with reason). Never fake a capability or return
  placeholder audio. See docs/CAPABILITIES.md.
- User-facing strings: Chinese UI, English code/comments where practical.
- Shell scripts: `set -euo pipefail`, idempotent, log what they do, explicit
  errors, **no silent deletion of user files** (cleanup requires confirmation).

## 3. Testing requirements

| Layer | Command | Requirement |
| --- | --- | --- |
| API / unit | `pytest tests/api` | 80 tests: upload validation, path traversal, capability gates, license consent, install-plan reuse, job cancel/retry, splice PCM preservation, legacy-endpoint regression. Fixtures isolate data/models dirs and never start the real worker — extend with every backend change; do not merge untested backend logic. |
| Frontend types | `cd app/frontend && npx tsc --noEmit` | Must pass with zero errors |
| UI automation | `cd tests/ui && node studio_test.mjs [--full]` | Playwright suite (35 checks incl. real generation end-to-end, light/dark, 1440/1280/narrow); update/extend when changing flows |
| Model regression | `scripts/verify_capabilities.py`, `scripts/run_quality_tests.py` | Required when touching inference/templates; record results in docs/TEST_REPORT.md. Uses the dev-only funasr ASR chain (see §5 license boundary). |

Manual checks for UI changes: light/dark themes, 1440×900 and 1280×800,
empty/error states, keyboard accessibility.

## 4. Pull request process

1. Fork / branch from `main`; keep PRs focused (one concern per PR).
2. Ensure: `tsc -b` passes, relevant tests pass, `./scripts/doctor.sh` clean.
3. Fill in the PR template checklist (tests, license impact, no weights/audio).
4. Update docs when behavior changes (README, CAPABILITIES, API_CONTRACT).
5. Maintainers review and squash-merge. Do not push tags or create releases
   yourself; releases are gated by docs/RELEASE_CHECKLIST.md.

### Commit convention & DCO

- Conventional-style messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:` (e.g., `fix(worker): release model on idle timeout`).
- We use the **Developer Certificate of Origin** instead of a CLA. Add a
  sign-off line to every commit:

  ```
  Signed-off-by: Your Name <your.email@example.com>
  ```

  (`git commit -s`). By signing off you certify the DCO v1.1
  (https://developercertificate.org/) — you have the right to submit the work
  under this project's license.

## 5. License boundaries (hard rules)

- **Never commit model weights** (`*.safetensors`, `*.pt`, `*.ckpt`, `*.bin`),
  **audio files** (uploads, outputs, test recordings), logs, `.env`, or
  personal data. `.gitignore` covers these; verify with `git ls-files` before
  pushing. Test audio in the repo must be synthetic/original with documented
  provenance (current test set is TTS-synthesized).
- **Do not vendor upstream AuK source** into this repo. We install it locally
  and call it. If a copy is ever unavoidable, retain Tencent's MIT notice and
  record the revision in THIRD_PARTY_NOTICES.md.
- **Do not add the funasr/kaldiio verification chain to runtime dependencies.**
  kaldiio's installed license is NTT evaluation-only (no redistribution) — it
  must stay dev-only. See docs/DEPENDENCIES_LICENSES.md §4.1.
- New dependencies must have permissive licenses (MIT/Apache-2.0/BSD/ISC).
  LGPL requires maintainer review; GPL/AGPL/SSPL/non-commercial licenses are
  rejected for runtime use.
- Do not claim or imply commercial usability of the full inference chain, and
  do not use Tencent/Alibaba logos or branding in UI assets.
- Voice cloning features: only use reference audio you have rights to; do not
  submit real people's recordings as demo material without written permission.

## 6. Reporting bugs / requesting features

Use the issue templates. For security issues, follow [SECURITY.md](SECURITY.md)
(private reporting, not public issues).

## 7. Code of conduct

Be respectful and constructive. This is a research/evaluation tool community;
harassment, impersonation of official projects, and sharing of unauthorized
voice recordings are not tolerated.