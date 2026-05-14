<!--
PR title must follow Conventional Commits:
  feat(scope): subject     — new user-facing capability
  fix(scope): subject      — bug fix
  refactor(scope): subject — internal change, no behavior change
  chore(scope): subject    — tooling / housekeeping
  docs(scope): subject     — docs only
  test(scope): subject     — tests only
  ci(scope): subject       — CI / GitHub Actions
  perf(scope): subject     — performance
  security(scope): subject — security-relevant change

Keep PRs SMALL. If this PR can't be reviewed in 15 minutes, split it.
-->

## What changed

<!-- One paragraph. What does this PR do? -->

## Why

<!-- The motivation. Which plan item / issue does this advance? -->

Closes #

## How tested

<!-- Concrete steps. "Ran X, saw Y." Not "tested locally." -->

- [ ] CI green
- [ ] Manually exercised (commands + observed output)
- [ ] Updated docs if behavior changed

## Risk & rollback

<!-- What could break? How would we revert? -->

**Risk:**
**Rollback:** `git revert <sha>` (this PR is a single squash commit; no migrations).

## Security checklist

- [ ] No secrets in code, commits, or logs
- [ ] No new attack surface (open ports, public endpoints, file writes outside namespace)
- [ ] If adding a dependency: pinned + reviewed
- [ ] If touching the VM: read `docs/vm-deploy.md` and obeyed the namespace rules
