# Contributing

This plugin is built **PR-driven** — one small, reviewable change per pull request. The dev workflow itself is part of the deliverable: every commit on `main` is independently revertable, every change passes CI, every PR documents what / why / how-tested / risk / rollback.

If you've never worked this way before: that's the point. Follow the steps below, open the PR, and read the review.

## Branching

- `main` is protected. No direct pushes. No force-pushes. CI must be green. 1 approving review.
- Feature branches: `<type>/<short-slug>` matching the conventional-commit type.
  - `feat/render-brief-html`
  - `fix/url-validation-edge-case`
  - `chore/pin-mcp-versions`
  - `docs/setup-doppler-quickstart`
  - `ci/add-bandit-scan`

## Conventional Commits

Every commit subject (and PR title — they end up the same after squash-merge) must start with one of:

- `feat:` — new user-facing capability
- `fix:` — bug fix
- `refactor:` — internal change, no behavior change
- `chore:` — tooling / housekeeping
- `docs:` — docs only
- `test:` — tests only
- `ci:` — CI / GitHub Actions
- `perf:` — performance
- `security:` — security-relevant change

Optional scope in parens: `feat(renderer): stream HTML as JSON arrives`.

Why: enables auto-generated changelogs and lets reviewers scan the history fast.

## PR checklist

The [PR template](.github/pull_request_template.md) prompts for everything. The two non-obvious ones:

- **Risk:** what could break? Be specific. "Possible XSS if a domain expert returns a URL with a non-http scheme" is useful; "minimal" is not.
- **Rollback:** how would we revert? For most PRs, `git revert <sha>` is enough — but if the change touches the VM or migrates data, write the rollback steps.

## Secrets — Doppler, never `.env`

**Never commit secrets. Never create a `.env` file in this repo.**

Local development uses [Doppler](https://www.doppler.com/):

```bash
doppler login
doppler setup --project research-company-ecosystem --config dev
doppler run -- claude
```

If Doppler isn't installed, export env vars in your shell — but never write them to a file in this repo. `.gitignore` blocks `.env*` (except `.env.example` if we ever ship one — currently we don't).

`gitleaks` runs in CI on every PR and will fail the build if a secret slips in.

## Lint & format

```bash
pip install ruff==0.6.9
ruff format .          # fix formatting
ruff check . --fix     # fix lint
```

CI runs `ruff format --check` and `ruff check` — no auto-fix in CI.

## Provider strategy (for when you're adding an upstream)

We use the Strategy pattern in `research-service/src/upstreams/<signal>/`. Each signal directory has:

- `_base.py` — abstract class with the JSON return shape every provider must conform to
- `<provider>.py` — concrete implementations (e.g. `exa.py`, `perplexity.py` for `search`)

Adding a new provider:

1. Implement the abstract methods in a new file.
2. Add a one-line entry in `providers.yaml` to enable it.
3. Existing route handlers don't change — they call `get_active_provider("<signal>").lookup(...)`.

Free-tier providers are the **default** in `providers.yaml`. Paid providers are stubs until configured.

## Tests

Adding behavior? Add a test. The renderer (`lib/render_brief.py`) has the highest test coverage because it's pure logic.

```bash
pytest -q
```

## Opening the PR

```bash
git checkout -b feat/<slug>
# ... make changes ...
git commit -m "feat(scope): subject"
git push -u origin feat/<slug>
gh pr create        # fill in the template
```

CI runs automatically. Fix anything red. Ask for review.

## Code review (Claude as the second developer)

Once a PR is open, run `/review` (or invoke the `code-reviewer` agent) on the diff. The review covers style, security, simplicity, missed edge cases — the same review another developer would do.

You can also invoke this on your OWN PRs before asking for human review. It catches the obvious stuff cheaply.
