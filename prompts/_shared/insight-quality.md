# Insight quality rubric

An **insight** has three properties an interview-grade observation must have. A **fact** doesn't. The point of this skill is to surface insights, not regurgitate facts.

## The three properties

### 1. Tension
There is a contradiction, asymmetry, or unresolved decision visible in the data. Two things are true that don't easily coexist, and the company is in the middle of resolving them.

### 2. Specificity
You can point to the exact evidence. Names, numbers, dates, URLs. "Their pricing page hides per-seat costs above 50 seats" — not "their pricing is complex."

### 3. Usefulness
The candidate can do something with it in an interview. Either:
- Admire it credibly ("I noticed X — that's a smart move because Y")
- Position themselves to help ("Y looks underinvested; I've shipped Z which would address it")
- Use as opener ("Saw you launched X last Tuesday — what's the metric you're hoping it moves?")

## Concrete examples

### ❌ Facts (not insights)

These belong in `raw_facts`, never in `insights`:

- "The company has customers in the US and Europe."
- "They use React on the frontend."
- "They raised a $14M Series A in 2024."
- "Their CEO has 12 years of experience."
- "They have a careers page with open roles."
- "Their product is used by software teams."
- "They focus on AI."

Each of these is true, generic, and tells the candidate nothing they couldn't get from the homepage. Useless.

### ✅ Insights (the bar)

**Sales (`weak`, high confidence):**
> "8 sales engineers, zero DevRel — enterprise pivot mid-flight despite developer-facing API"
> *Evidence:* LinkedIn shows 8 SE roles posted since Jan; team page has no DevRel headcount; API docs require a sales call to get a key. They're moving upmarket but haven't built the developer-experience layer that justifies the API positioning. **Tension:** product surface and GTM motion don't match yet.

**Money (`opening`, medium confidence):**
> "Series B announced 6 weeks ago names 'EU expansion' but careers page only hires in US"
> *Evidence:* TechCrunch announcement explicitly mentions Frankfurt office; LinkedIn jobs filter shows 22 US-only postings, 0 EU. **Opening:** if you're interviewing for anything ops/expansion-adjacent, ask what's blocking the EU build-out.

**R&D / Tech (`fun`, medium confidence):**
> "Engineering blog post titled 'why we replaced Kafka with Postgres LISTEN/NOTIFY'"
> *Evidence:* Blog post dated last month; author is the principal engineer. They picked boring infrastructure publicly. **Fun opener:** "I loved your Postgres post — what was the breaking point that made you cut Kafka?"

**Hiring (`weak`, high confidence):**
> "12 of 14 open eng roles are senior+ — they're not training, they're buying"
> *Evidence:* Careers page filtered to engineering shows 12 senior/staff roles, 2 mid. No intern or new-grad program. **Tension:** at 80 engineers, that mix is unsustainable in 18 months — bottlenecks at the senior level, no farm system. A weak point the candidate could credibly say they'd want to help with.

**Customers (`contradiction`, medium confidence):**
> "Logo wall lists 6 enterprise brands but G2 reviews are 90% from <50-person startups"
> *Evidence:* Homepage shows Microsoft, Snowflake, etc.; G2 segment chart shows 87% small business. **Tension:** they sell the enterprise story but the actual buyer profile is much smaller. Implies the enterprise logos are POCs, not ARR.

### How to spot these in your domain

For your specific domain, what does **tension** look like? What signals does the **specific** evidence come from? What does the **useful** action for a candidate look like? Your domain prompt has heuristics — but the best ones are the ones you discover. **Edit your domain prompt file** with new heuristics whenever you find a pattern that works.

## The "would another candidate find this?" test

Before submitting an insight, ask: would a candidate who spent 20 minutes on the company's homepage and LinkedIn find this? If yes — it's a fact, drop it. If only you found it because you correlated across two signals (e.g., hiring page + engineering blog + reviews), it's an insight.
