# Security Policy

## 1. Threat model: a local-only workbench

AuK Studio is designed as a **single-user, local-first** application:

- The HTTP server binds to **`127.0.0.1` only** by default (`AUK_HOST=127.0.0.1`
  in `.env.example`; see `app/backend/config.py`). It is not reachable from the
  network unless you deliberately change this.
- All inference runs on-device (MLX / Metal). **No audio, voice templates, or
  telemetry are uploaded to any external server.** The only outbound network
  traffic is user-initiated model downloads from official sources (and package
  installation during setup).
- Uploaded files are stored under random IDs inside `data/`; downloads are
  confined to the data directory; original uploads are kept read-only.
- There is no endpoint that executes arbitrary shell commands. Subprocess use
  is limited to controlled, parameterized invocations (ffmpeg, model
  conversion).

### Known risk: the local API has no authentication

The local API (`http://127.0.0.1:<port>/api`) is **unauthenticated by design**,
because it is meant for the same machine's browser only. Consequences:

- **Any process or local user on the same machine can call the API** (create
  jobs, read outputs, delete audio). On a shared machine, treat the workbench
  as accessible to other local accounts.
- **Do not expose the port to the public internet** — no `0.0.0.0` binding, no
  router port-forwarding, no reverse proxy without adding your own
  authentication and TLS. An exposed instance would let anyone run inference
  on your hardware and read your audio.
- Browser-based attacks: a malicious web page could attempt requests against
  `127.0.0.1`. Keep the default loopback binding, and be aware that loopback
  services without auth are reachable from any browser on the machine.
- Do not point `AUK_DATA_DIR` / `AUK_MODELS_DIR` at sensitive locations.

If you need multi-user or remote access, that is out of scope for this project
and requires adding authentication, authorization, and TLS yourself.

## 2. Reporting a vulnerability

Please **do not open public issues for security problems**.

- Preferred: GitHub Security Advisories — use the repository's
  **"Report a vulnerability"** button (Security tab → Advisories).
  *(Placeholder: enabled once the repository is public.)*
- If private advisories are unavailable, contact the maintainers privately
  (contact address to be added before public release).

Please include: affected version/commit, reproduction steps, impact, and any
suggested fix. We aim to acknowledge reports within 7 days.

Scope notes:

- Vulnerabilities in **upstream AuK** should also be reported to
  https://github.com/Tencent-Hunyuan/AuK.
- Model behavior (e.g., unexpected outputs) is generally not a security issue;
  model license questions belong in docs/MODEL_LICENSES.md discussions.

## 3. Supply chain: model downloads

The downloader (`scripts/download_models.py`, invoked by
`scripts/download_models.sh`) follows these rules:

- **Fixed allowlist of official repositories only** — `tencent/AuK-Flash`,
  `tencent/AuK`, `Qwen/Qwen2.5-Omni-3B` and their ModelScope mirrors
  (`Tencent-Hunyuan/*`, `Qwen/*`). No arbitrary URLs are accepted.
- **HTTPS only**; HuggingFace fallback goes through a user-configured SOCKS
  proxy (`HF_PROXY`), ModelScope is direct.
- **sha256 verification** of weight files against hashes recorded in
  `config/model_manifest.json` (obtained from the HuggingFace official API).
  Checksum mismatch deletes the partial file and aborts.
  *Known gap:* small metadata files (config/tokenizer/LICENSE) are currently
  verified by size only, not sha256 — tracked in docs/RELEASE_CHECKLIST.md.
- Resumable chunked downloads with retry; progress is logged to
  `logs/download.log`.
- The downloader never executes downloaded content as code; weights are
  loaded via `safetensors` (no pickle execution). Conversion uses the upstream
  `auk_mlx.convert` module from the pinned revision.
- No `curl | bash`, no silent `sudo`. System-level installs (Homebrew packages,
  uv, Node) are left to the user.

**User responsibilities:** only download models through the provided scripts
or official channels; verify you have the right to use any reference audio you
upload; keep `.env` private (it is git-ignored).

## 4. Data handling

- `data/`, `logs/`, `backups/`, `.env`, and all model weights are git-ignored.
- Backups (`scripts/backup.sh`) stay local; `--with-audio` includes your
  recordings — store such archives accordingly.
- No analytics, no crash reporting, no cloud API keys are configured or
  required. (`opentelemetry-api` exists only as an unused transitive API
  package; no SDK/exporter is installed and no code references it.)

## 5. Supported versions

Pre-1.0: only the latest `main` revision receives security fixes.