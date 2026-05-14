# Output schema — the JSON contract

Return EXACTLY this JSON block, nothing before it, nothing after it. No backticks, no commentary.

```json
{
  "domain": "<one of: market | sales | product | rd | traffic | people | hiring | customers | money>",
  "insights": [
    {
      "id": "<domain>-1",
      "tag": "strong | weak | fun | opening | contradiction",
      "headline": "<= 90 chars, one line, no trailing period",
      "evidence": "2-4 sentences explaining what you found and why it matters",
      "sources": [
        { "title": "Short source label", "url": "https://..." }
      ],
      "confidence": "high | medium | low",
      "tools_used": ["WebSearch", "mcp__firecrawl__scrape", "..."]
    }
  ],
  "raw_facts": [
    "Plain facts you observed but didn't elevate to insights (the synthesis pass uses these to find cross-domain contradictions)"
  ],
  "gaps": [
    "Things you tried to verify but couldn't, or signals you'd want with more tool budget"
  ]
}
```

## Field rules

- **`domain`** — exactly the slug provided in your prompt. Must match.
- **`insights`** — 2 to 3 items. Three is the cap. Two excellent insights beats three padded.
- **`id`** — `<domain>-N`. Use 1-indexed integers.
- **`tag`** — pick the BEST fit, not the safest:
  - `strong` — a genuine differentiator the candidate can credibly admire
  - `weak` — a fixable problem the candidate could plausibly help with (most useful for interviews)
  - `fun` — a memorable, easy opener; surprising or quirky
  - `opening` — a specific concrete thing the candidate can name-drop (a recent launch, a person's tenure milestone, a product they shipped last week)
  - `contradiction` — only use this if YOU spotted a tension inside your own domain. Cross-domain contradictions get added by the synthesis pass.
- **`headline`** — must be readable on its own. No "this company has..." filler. Lead with the insight.
- **`evidence`** — 2-4 sentences. What you saw, where, why it matters. No fluff.
- **`sources`** — at least 1, ideally 2-3. URLs must be real, fetched URLs.
- **`confidence`** — see `identity-rules.md`. Be honest.
- **`tools_used`** — which tools you actually invoked for this specific insight. Used by telemetry and the verifier.
- **`raw_facts`** — anything you observed but didn't elevate. The verifier scans these across all 9 domains for numerical contradictions (e.g., "headcount ~120" from People vs "headcount ~200" from Money).
- **`gaps`** — be candid. "Couldn't verify pricing — page returned 403" is useful. The user reads gaps to know what they'd need to confirm manually.

## What breaks the renderer

- Trailing comma in JSON
- Single quotes instead of double quotes
- Missing required field
- URL with a non-http(s) scheme
- Newlines inside string values (use spaces or `\n` escape)
- Anything before or after the JSON block
