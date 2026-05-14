# Tools — what to use for what

This is the **per-domain default tool playbook**. Each domain expert has its own tool budget (default `MAX_TOOL_CALLS=3`). Use this as the prior; the expert's own heuristics override.

## Default stack (free-tier, works without any API keys)

| Domain | First-choice tool | What it gives you |
|---|---|---|
| Market | `mcp__exa__web_search_exa` (1K req/mo free) → `WebFetch` for top 1-2 results | Competitive landscape, recent shifts, analyst mentions |
| Sales | `mcp__firecrawl__firecrawl_scrape` on `<url>/pricing` and `<url>/customers`; `WebSearch "{company} G2 reviews"` | Pricing motion, deal-size hints, sales-engineer ratio (LinkedIn) |
| Product | `mcp__firecrawl__firecrawl_scrape` on `<url>/changelog` or `<url>/blog`; `WebSearch "{company} launch"` | Recent shipping cadence, what they ripped out, what's new |
| R&D / Tech | Wappalyzer OSS CLI (`bash {{plugin_dir}}/scripts/wappalyzer.sh <url>`); `mcp__firecrawl__firecrawl_scrape` on engineering blog | Frontend/backend stack, infra choices, engineering culture |
| Traffic | `WebSearch "{company} {category} alternatives"` (do they rank?); `WebFetch <url>` for SEO hygiene check | SEO position, content cadence, paid presence hints |
| People | `mcp__linkedin__company_profile` (free, opt-in); `WebFetch <url>/about` | Org size, leadership, recent senior hires, tenure |
| Hiring | `mcp__linkedin__search_jobs` for `{company}`; `WebFetch <url>/careers` | Open roles by function, leveling, geography |
| Customers | `WebSearch "{company} G2 reviews"`; `mcp__firecrawl__firecrawl_scrape` on G2/Capterra; HN/Reddit search | Logo-wall vs reality, recurring complaints, sentiment |
| Money | `WebSearch "{company} funding"`; SEC EDGAR (no key, US public); OpenCorporates (free for personal use) | Funding history, runway hints, recent press |

## Optional paid upgrades (when configured)

| Domain | Paid tool | Why upgrade |
|---|---|---|
| Market, Money | `mcp__perplexity__ask_perplexity` | Better synthesized research with citations |
| Traffic | Semrush API wrapper (in service) | Real organic traffic numbers, keyword rankings |
| R&D / Tech | Wappalyzer paid API (`mcp__wappalyzer__lookup_site`) | More accurate fingerprinting, more categories |
| Money | Crunchbase API wrapper (in service) | Structured funding rounds, exec comp |
| People, Hiring | Apollo API wrapper (in service) | Richer people data, contact info |

When paid versions are available, they are preferred only if their `_base.py` JSON return shape adds signal — same JSON, more reliable.

## Hard rules for tool selection

1. Check `AVAILABLE_TOOLS` (passed in your runtime context) before calling anything.
2. Prefer ONE good tool call to three mediocre ones — `MAX_TOOL_CALLS=3` is a hard ceiling.
3. Cache hits cost nothing; the same Firecrawl scrape used by 3 different experts in one run is fine.
4. If a tool returns 403, 429, or empty results — log to `gaps` and try ONE alternate; don't burn budget retrying the same call.

## Future tools (not yet wired)

- Service endpoint `POST /domain/{slug}` — when the backend service is reachable, this single call replaces the per-domain tool playbook above. Cheaper (shared cache) and more consistent.
