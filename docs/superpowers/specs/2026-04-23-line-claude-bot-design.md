# LINE Claude Bot Design
Date: 2026-04-23

## Goal
A lightweight LINE Bot that calls the Anthropic Claude API directly, deployable to Railway free tier. Runs 24/7 without requiring the user's Mac to be on.

## Architecture
Single-file FastAPI webhook server. No database. In-memory conversation history per user.

```
LINE → Railway HTTPS → FastAPI /webhook → Anthropic API → LINE Reply API
```

## Components

### main.py
- FastAPI app with POST `/webhook` endpoint
- LINE HMAC-SHA256 signature verification
- In-memory dict keyed by LINE user ID storing message history
- Calls `anthropic.messages.create()` with full conversation history
- Replies via LINE Reply API using the reply token

### Conversation History
- Structure: `dict[user_id, list[{"role", "content"}]]`
- Max 20 messages per user (10 exchanges), oldest dropped when exceeded
- Cleared on server restart (acceptable for personal use)

### Files
- `main.py` — entire application logic
- `requirements.txt` — fastapi, uvicorn, anthropic, httpx
- `railway.json` — Railway deployment config

## Environment Variables
Set in Railway dashboard, never in code:
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `ANTHROPIC_API_KEY`

## Deployment
Railway free tier ($5/month credit). Service sleeps when idle; wakes on incoming webhook (first response may take 10-30s).

## Constraints
- No persistent storage — history lost on restart
- Single-user focus (personal LINE bot)
- No group chat support in v1
