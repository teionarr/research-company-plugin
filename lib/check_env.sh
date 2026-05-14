#!/usr/bin/env bash
# check_env.sh — emit the AVAILABLE_TOOLS allowlist that domain experts pass through to
# their tool-call decisions, plus a few related env-detection lines.
#
# Output: KEY=VALUE lines on stdout, suitable for `eval $(check_env.sh)` or for parsing.
# Errors and notes go to stderr.
#
# Reads from the process environment (which Doppler may have populated via `doppler run`).
# Does NOT read .env files. Does NOT print any secret values — only their presence.
#
# Detected tools:
#   - claude_websearch    (always available — built into Claude Code)
#   - claude_webfetch     (always available)
#   - exa                 (requires EXA_API_KEY; free tier 1K req/mo)
#   - perplexity          (requires PERPLEXITY_API_KEY; paid only)
#   - firecrawl           (requires FIRECRAWL_API_KEY; free tier 1K credits/mo)
#   - wappalyzer_oss      (requires `wappalyzer` or `wappybird` binary on PATH; free, local)
#   - wappalyzer_api      (requires WAPPALYZER_API_KEY; paid)
#   - linkedin_mcp        (requires LINKEDIN_SESSION_COOKIE; free, opt-in, ToS gray)
#   - apollo              (requires APOLLO_API_KEY; free tier 60 credits/mo)
#   - crunchbase          (requires CRUNCHBASE_API_KEY; paid)
#   - semrush             (requires SEMRUSH_API_KEY; paid)
#   - sec_edgar           (always available — public API, no key)
#   - opencorporates      (requires OPENCORPORATES_API_KEY for higher rate limits;
#                          works without key for personal-use rate limit)

set -euo pipefail

emit() {
    printf '%s=%s\n' "$1" "$2"
}

note() {
    printf 'check_env: %s\n' "$1" >&2
}

# Always-available baselines
available=("claude_websearch" "claude_webfetch" "sec_edgar" "opencorporates")

# Doppler status (informational only)
if command -v doppler >/dev/null 2>&1; then
    if doppler configure get project >/dev/null 2>&1; then
        proj=$(doppler configure get project --plain 2>/dev/null || echo unknown)
        cfg=$(doppler configure get config --plain 2>/dev/null || echo unknown)
        emit DOPPLER_STATUS "configured:${proj}/${cfg}"
    else
        emit DOPPLER_STATUS "installed_not_configured"
        note "doppler is installed but no config is set — falling back to shell env vars"
    fi
else
    emit DOPPLER_STATUS "not_installed"
fi

# API-key-gated tools
[[ -n "${EXA_API_KEY:-}" ]]              && available+=("exa")
[[ -n "${PERPLEXITY_API_KEY:-}" ]]       && available+=("perplexity")
[[ -n "${FIRECRAWL_API_KEY:-}" ]]        && available+=("firecrawl")
[[ -n "${WAPPALYZER_API_KEY:-}" ]]       && available+=("wappalyzer_api")
[[ -n "${LINKEDIN_SESSION_COOKIE:-}" ]]  && available+=("linkedin_mcp")
[[ -n "${APOLLO_API_KEY:-}" ]]           && available+=("apollo")
[[ -n "${CRUNCHBASE_API_KEY:-}" ]]       && available+=("crunchbase")
[[ -n "${SEMRUSH_API_KEY:-}" ]]          && available+=("semrush")

# Local binary detection
if command -v wappalyzer >/dev/null 2>&1 || command -v wappybird >/dev/null 2>&1; then
    available+=("wappalyzer_oss")
fi

# Service backend reachability (the kitchen)
if [[ -n "${RESEARCH_SERVICE_URL:-}" ]]; then
    if curl --silent --max-time 2 --fail "${RESEARCH_SERVICE_URL}/health" >/dev/null 2>&1; then
        emit RESEARCH_SERVICE_REACHABLE "true"
        emit RESEARCH_SERVICE_URL "${RESEARCH_SERVICE_URL}"
    else
        emit RESEARCH_SERVICE_REACHABLE "false"
        note "RESEARCH_SERVICE_URL set but /health unreachable — falling back to direct MCP/API calls"
    fi
else
    emit RESEARCH_SERVICE_REACHABLE "false"
fi

# Brief output directory
emit BRIEF_OUTPUT_DIR "${BRIEF_OUTPUT_DIR:-${HOME}/Documents/research-company-briefs}"

# Print the allowlist as a comma-separated string
allowlist=$(IFS=,; echo "${available[*]}")
emit AVAILABLE_TOOLS "${allowlist}"
emit AVAILABLE_TOOLS_COUNT "${#available[@]}"
