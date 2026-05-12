# LINE Bot CPS + OpenEvidence Design
Date: 2026-05-04

## Goal
Upgrade the existing LINE Claude bot to perform CPS-style clinical diagnostic reasoning and search OpenEvidence for medical literature, running fully on Render (no Mac dependency).

## Architecture

```
LINE User
  │
  ▼
Render FastAPI (main.py)
  │  1. Verify LINE signature
  │  2. Build CPS system prompt + conversation history
  ▼
Anthropic API (claude-sonnet-4-6) with tool_use
  │  tool: search_evidence(question)
  │  triggered only when literature is needed
  ▼
OpenEvidenceClient (embedded in main.py)
  │  POST openevidence.com/api/article
  │  GET  openevidence.com/api/article/{id} (polling)
  │  Cookies from Render env var OE_COOKIES_JSON
  ▼
Literature summary returned to Claude
  │
  ▼
Claude completes CPS reasoning → LINE reply (1–5 messages)
```

## Components

### CPS System Prompt
Constant string embedded in `main.py`. Contains condensed CPS reasoning structure:

1. **Problem representation** — one-sentence patient summary
2. **DDx Top 5–8** — diagnoses with pre-test probability (%)
3. **Must-not-miss** — red flag diagnoses regardless of probability
4. **Key discriminators** — supporting vs. opposing evidence per diagnosis
5. **Evidence search** — call `search_evidence` tool when needed (rare diagnosis, current guidelines, close probabilities)
6. **Bayesian update** — adjust probabilities based on literature
7. **Conclusion** — most likely diagnosis + recommended next workup/management

Output: structured Traditional Chinese, include LR+/LR− values when known.

Estimated size: ~800–1200 tokens.

### OpenEvidenceClient Class
Embedded in `main.py`. Uses browser session cookies to call the internal OpenEvidence REST API.

**Initialization:**
- Read `OE_COOKIES_JSON` env var (JSON string matching cookies.json format)
- Parse into cookie dict for HTTP requests

**`ask(question: str) -> str`:**
1. `POST /api/article` with question payload + cookies
2. Extract `article_id` from response
3. Poll `GET /api/article/{article_id}` every 3s, up to 60s timeout
4. Return answer text (plain text only, no figures)

**Error handling:**
- 401 (cookies expired) → return `"[文獻搜尋暫時無法使用，請更新 Cookies]"`
- Timeout (60s) → return `"[文獻搜尋逾時]"`
- In both cases, Claude continues reasoning with training knowledge; conversation is not interrupted.

**Cookies refresh procedure (every ~2–4 weeks):**
```bash
python ~/openevidence-mcp/extract_chrome_cookies.py
# Copy output JSON → Render env var OE_COOKIES_JSON → Redeploy
```

### Tool Use Message Flow
Extends existing conversation history to support `tool_use` and `tool_result` message types.

```
user msg → API call
  if stop_reason == "tool_use":
    1. Append assistant tool_use block to history
    2. Execute search_evidence(question)
    3. Append user tool_result block to history
    4. Second API call with full history
  if stop_reason == "end_turn":
    Extract text → split → reply to LINE → append to history
```

**New history entry formats:**
```python
# assistant tool call
{"role": "assistant", "content": [{"type": "tool_use", "id": "...", "name": "search_evidence", "input": {"question": "..."}}]}

# tool result
{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "...literature summary..."}]}
```

### Message Splitting
LINE Reply API supports up to 5 messages per reply, each up to 5000 characters.

```python
def split_message(text: str, limit: int = 4800) -> list[str]:
    # Split on paragraph boundaries to avoid mid-sentence cuts
    # Return list of at most 5 chunks
    # Truncate if total exceeds 5 chunks (>24000 chars; won't occur in practice)
```

Reply payload:
```python
"messages": [{"type": "text", "text": chunk} for chunk in chunks]
```

## Environment Variables
All set in Render dashboard:

| Variable | Description |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API token |
| `LINE_CHANNEL_SECRET` | LINE webhook signature secret |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OE_COOKIES_JSON` | Full JSON content of openevidence-mcp/cookies.json |

## Files Changed
- `main.py` — all changes; no new files needed

## Constraints
- No persistent storage — history and cookies in memory/env var
- Single API call nesting: tool_use → tool_result → final reply (no recursive tool chains)
- OpenEvidence is unofficial (cookie-based); may break if their API changes
- LINE replyToken expires in ~60s from webhook receipt. OpenEvidence polling timeout is set to **45s** (not 60s) to leave margin for Claude's second API call. If OE exceeds 45s, fall back to training knowledge and still reply within the window.
- If LINE replyToken expires before reply is sent, the message is silently dropped. Mitigation: keep total processing time under 55s (OE 45s + Claude ~5s + network ~5s).
