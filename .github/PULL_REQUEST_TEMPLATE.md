# Pull Request

## Summary

What does this PR change and why?

## Related issue

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature (capability-gated, see below)
- [ ] Refactor / chore
- [ ] Docs / compliance
- [ ] Tests

## Checklist

### Tests
- [ ] `cd app/frontend && npx tsc -b` passes
- [ ] Relevant pytest / UI automation tests added or updated and passing
- [ ] Model-touching changes: regression run recorded (scripts/verify_capabilities.py / run_quality_tests.py)
- [ ] Manual UI check (light/dark, empty/error states) if UI changed

### Capability gating (if inference/UI entries touched)
- [ ] UI reflects config/capabilities.json; no capability marked supported without real generated-audio evidence
- [ ] Experimental features carry the experimental badge; unsupported entries stay disabled

### License & compliance
- [ ] No model weights (`*.safetensors/*.pt/*.ckpt/*.bin`), audio files, logs, `.env`, or personal data added (`git ls-files` checked)
- [ ] No upstream AuK source vendored; no Tencent/Alibaba branding assets
- [ ] New dependencies are permissively licensed; docs/DEPENDENCIES_LICENSES.md + THIRD_PARTY_NOTICES.md updated if deps changed
- [ ] funasr/kaldiio chain NOT added to runtime dependencies
- [ ] No claim of commercial usability of the Qwen-dependent inference chain

### Process
- [ ] Commits signed off (DCO, `git commit -s`)
- [ ] Docs updated (README / CAPABILITIES / API_CONTRACT) where behavior changed
- [ ] Scripts remain idempotent, logged, and do not silently delete user files

## Notes for reviewers

Anything tricky, known limitations, follow-up work.