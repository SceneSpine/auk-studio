---
name: Feature request
about: Suggest a capability or improvement for AuK Studio
title: "[Feature] "
labels: enhancement
assignees: ''
---

<!--
Capability gating reminder (docs/CAPABILITIES.md):
- AuK official support does NOT imply MLX-branch support. Features are gated by
  real on-device verification: supported / unverified (experimental) / not_supported.
- Currently NOT supported on MLX: speech enhancement (denoise/dereverb),
  source separation, ASR/forced alignment in the workbench.
- Emotion editing is experimental (unverified) — improvements welcome, but
  claims need objective evidence.
- Any feature must respect the Qwen Research License (non-commercial) boundary.
-->

## Problem / motivation

What workflow is blocked or painful today?

## Proposed solution

What you'd like to happen. If this is a new model capability, note whether the
upstream MLX branch (`feat/mlx-apple-silicon`) implements it, with a source
reference if possible.

## Capability gate check

- [ ] I checked docs/CAPABILITIES.md and config/capabilities.json
- [ ] This does not require a capability marked `not_supported` without upstream MLX implementation
- [ ] I understand new capabilities need real generated audio + verification before being marked `supported`

## Alternatives considered

Other approaches or workarounds (e.g., different seed, Base variant, splice export).

## License / rights impact

Does this involve new dependencies, model weights, or audio素材? New runtime
dependencies must be permissively licensed; weights and third-party recordings
are never committed. See CONTRIBUTING.md §5.

## Additional context

Mockups, references, related issues.