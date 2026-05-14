# `/research-company`

A Claude Code plugin that researches a company across 9 business domains in parallel — Market, Sales, Product, R&D/Tech, Traffic, People, Hiring, Customers, Money — and produces a single self-contained HTML brief with verified, non-obvious insights you can use in a job interview.

> **Status: scaffold (v0.1.0).** The plugin manifest, CI, and dev workflow are in place. Functional slices land via PRs `feat/...` — see [the project plan](#project-plan).

## What it produces

A single HTML file with:

- **Top 5 insights** to use in your interview (always visible)
- 9 collapsible domain sections, each with 2-3 insights
- Each insight tagged: 💪 strong · 🔧 weak (good problem) · ✨ fun · 🎯 opening · 🔀 contradiction
- Source citations on every claim, HEAD-checked for liveness
- Verification badge per insight (`verified` / `inferred` / `unsupported`)
- Cross-domain contradictions surfaced explicitly

## Quick install (once functional slices land)

```bash
# Clone or install via Claude Code plugin manager
git clone https://github.com/teionarr/research-company-plugin.git
/plugin install ./research-company-plugin

# Run
/research-company "Stripe" "applying for product manager"
```

## Setup

The plugin works out of the box on the **free-tier-only path** — no API keys, no payments required. See [`docs/SETUP.md`](docs/SETUP.md) (lands in a later PR) for the full menu.

**Recommended:** [Doppler](https://www.doppler.com/) for secrets management.

```bash
brew install dopplerhq/cli/doppler
doppler login
doppler setup --project research-company-ecosystem --config dev
doppler run -- claude    # all API keys (when configured) injected automatically
```

**Fallback:** export env vars in your shell — no `.env` files. See `docs/CONTRIBUTING.md`.

## Free-tier-only default stack

| Signal | Provider | Free tier |
|---|---|---|
| Search | Exa MCP + Claude WebSearch | Exa: 1000 req/mo |
| Scraping | Firecrawl MCP | 1000 credits/mo |
| Tech stack | Wappalyzer OSS CLI (local) | unlimited |
| Funding | SEC EDGAR + OpenCorporates + Wikipedia | unlimited |
| People | LinkedIn MCP (session-based) | unlimited (opt-in) |
| Hiring | Firecrawl on careers pages | uses Firecrawl quota |
| Traffic | Google Trends + free SimilarWeb pages | unlimited / scraped |

Paid upgrades (Perplexity, Crunchbase, Semrush, Apollo, Wappalyzer paid) are opt-in via one config flip — see [provider strategy](docs/CONTRIBUTING.md#provider-strategy).

## Project plan

See the canonical plan at [`docs/PLAN.md`](docs/PLAN.md) (lands in PR-1.2 alongside the prompts).

The plugin is being built **PR-driven, one atomic slice at a time** — that's the point. Open PRs against `main` are gated by CI (lint, secret scan, schema validation).

## Prior art & credits

- [priankr/claude-skill-company-research](https://github.com/priankr/claude-skill-company-research) — different approach (sequential markdown report); credit for the original idea.
- [Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server), [Exa MCP](https://github.com/exa-labs/exa-mcp-server), [Perplexity MCP](https://github.com/tanigami/mcp-server-perplexity), [Wappalyzer MCP](https://github.com/wappalyzer/mcp) — the MCP ecosystem this plugin builds on.
- [Doppler](https://www.doppler.com/) — secrets management.

## License

MIT — see [LICENSE](LICENSE).
