# LINE Claude Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI webhook server that connects LINE Bot to Claude API, deployable to Railway free tier.

**Architecture:** Single `main.py` handles signature verification, in-memory conversation history (max 20 messages per user), Anthropic API calls, and LINE reply. No database, no external dependencies beyond the four pip packages.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, anthropic SDK, httpx

---

### Task 1: Project scaffold

**Files:**
- Create: `line-claude-bot/requirements.txt`
- Create: `line-claude-bot/railway.json`
- Create: `line-claude-bot/.env.example`

- [ ] **Step 1: Create requirements.txt**

```
fastapi
uvicorn[standard]
anthropic
httpx
pytest
pytest-asyncio
httpx
```

- [ ] **Step 2: Create railway.json**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] **Step 3: Create .env.example**

```
LINE_CHANNEL_ACCESS_TOKEN=your_token_here
LINE_CHANNEL_SECRET=your_secret_here
ANTHROPIC_API_KEY=your_key_here
```

- [ ] **Step 4: Install dependencies**

```bash
cd line-claude-bot
pip install -r requirements.txt
```

Expected: packages install without error.

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/
git commit -m "chore: scaffold line-claude-bot project"
```

---

### Task 2: LINE signature verification

**Files:**
- Create: `line-claude-bot/main.py`
- Create: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing test**

Create `line-claude-bot/test_main.py`:

```python
import base64
import hashlib
import hmac
import pytest

FAKE_SECRET = "testsecret"
FAKE_BODY = b'{"events":[]}'

def make_signature(secret: str, body: bytes) -> str:
    hash = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(hash).decode()

def test_verify_signature_valid():
    from main import verify_signature
    sig = make_signature(FAKE_SECRET, FAKE_BODY)
    assert verify_signature(FAKE_BODY, sig, FAKE_SECRET) is True

def test_verify_signature_invalid():
    from main import verify_signature
    assert verify_signature(FAKE_BODY, "badsignature", FAKE_SECRET) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd line-claude-bot
pytest test_main.py::test_verify_signature_valid -v
```

Expected: `ImportError` or `ModuleNotFoundError` (main.py doesn't exist yet).

- [ ] **Step 3: Create main.py with verify_signature**

Create `line-claude-bot/main.py`:

```python
import base64
import hashlib
import hmac
import json
import os
from collections import defaultdict

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

history: dict[str, list[dict]] = defaultdict(list)
MAX_HISTORY = 20


def verify_signature(body: bytes, signature: str, secret: str = LINE_CHANNEL_SECRET) -> bool:
    h = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(h).decode()
    return hmac.compare_digest(expected, signature)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest test_main.py::test_verify_signature_valid test_main.py::test_verify_signature_invalid -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add LINE signature verification"
```

---

### Task 3: Conversation history manager

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `line-claude-bot/test_main.py`:

```python
def test_add_message_and_trim():
    from main import add_message, history, MAX_HISTORY
    history.clear()
    user_id = "U123"
    for i in range(25):
        role = "user" if i % 2 == 0 else "assistant"
        add_message(user_id, role, f"message {i}")
    assert len(history[user_id]) == MAX_HISTORY

def test_history_order_preserved():
    from main import add_message, history
    history.clear()
    user_id = "U456"
    add_message(user_id, "user", "first")
    add_message(user_id, "assistant", "second")
    assert history[user_id][0]["content"] == "first"
    assert history[user_id][1]["content"] == "second"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test_main.py::test_add_message_and_trim test_main.py::test_history_order_preserved -v
```

Expected: `ImportError: cannot import name 'add_message'`

- [ ] **Step 3: Add add_message to main.py**

Append to `line-claude-bot/main.py` after the `history` declaration:

```python
def add_message(user_id: str, role: str, content: str) -> None:
    history[user_id].append({"role": role, "content": content})
    if len(history[user_id]) > MAX_HISTORY:
        history[user_id] = history[user_id][-MAX_HISTORY:]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest test_main.py::test_add_message_and_trim test_main.py::test_history_order_preserved -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add conversation history manager"
```

---

### Task 4: Webhook endpoint

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `line-claude-bot/test_main.py`:

```python
import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

def make_line_body(user_id: str, text: str, reply_token: str = "token123") -> bytes:
    return json.dumps({
        "events": [{
            "type": "message",
            "replyToken": reply_token,
            "source": {"userId": user_id},
            "message": {"type": "text", "text": text}
        }]
    }).encode()

def make_sig(body: bytes) -> str:
    h = hmac.new(FAKE_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode()

def test_webhook_invalid_signature():
    from main import app
    client = TestClient(app)
    response = client.post("/webhook", content=b"{}", headers={"X-Line-Signature": "bad"})
    assert response.status_code == 401

def test_webhook_valid_returns_ok():
    from main import app, history
    history.clear()
    body = make_line_body("Uabc", "hello")
    sig = make_sig(body)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hi there!")]

    with patch("main.LINE_CHANNEL_SECRET", FAKE_SECRET), \
         patch("main.claude.messages.create", return_value=mock_response), \
         patch("main.send_reply", new_callable=AsyncMock):
        from main import app
        client = TestClient(app)
        response = client.post("/webhook", content=body, headers={"X-Line-Signature": sig})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test_main.py::test_webhook_invalid_signature test_main.py::test_webhook_valid_returns_ok -v
```

Expected: failures (endpoint doesn't exist yet).

- [ ] **Step 3: Add send_reply and webhook endpoint to main.py**

Append to `line-claude-bot/main.py`:

```python
async def send_reply(reply_token: str, message: str) -> None:
    async with httpx.AsyncClient() as http:
        await http.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": message}],
            },
            timeout=10.0,
        )


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(body)

    for event in data.get("events", []):
        if event.get("type") != "message":
            continue
        if event.get("message", {}).get("type") != "text":
            continue

        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]
        user_text = event["message"]["text"]

        add_message(user_id, "user", user_text)

        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=history[user_id],
        )

        assistant_text = response.content[0].text
        add_message(user_id, "assistant", assistant_text)

        await send_reply(reply_token, assistant_text)

    return JSONResponse(content={"status": "ok"})
```

- [ ] **Step 4: Run all tests**

```bash
pytest test_main.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add webhook endpoint and LINE reply"
```

---

### Task 5: Deploy to Railway

**Files:** none (Railway config already in railway.json)

- [ ] **Step 1: Install Railway CLI**

```bash
npm install -g @railway/cli
```

- [ ] **Step 2: Login to Railway**

```bash
railway login
```

Expected: browser opens for OAuth login.

- [ ] **Step 3: Create Railway project**

```bash
cd line-claude-bot
railway init
```

When prompted: create a new project, name it `line-claude-bot`.

- [ ] **Step 4: Set environment variables**

```bash
railway variables set LINE_CHANNEL_ACCESS_TOKEN=你的token
railway variables set LINE_CHANNEL_SECRET=你的secret
railway variables set ANTHROPIC_API_KEY=你的key
```

取得 ANTHROPIC_API_KEY：在 Claude Code 終端機執行 `echo $ANTHROPIC_API_KEY`。

- [ ] **Step 5: Deploy**

```bash
railway up
```

Expected: build log shows `Uvicorn running on ...`, deployment URL printed.

- [ ] **Step 6: Get deployment URL and update LINE webhook**

```bash
railway domain
```

複製輸出的 URL（例如 `https://line-claude-bot-production.up.railway.app`），加上 `/webhook`，填入 LINE Developer Console → Webhook URL。

點 **Verify** 確認回傳 200。

- [ ] **Step 7: Test end-to-end**

用 LINE 傳訊息給 Bot，確認有回覆。

---

## Final Check

執行全部測試：

```bash
cd line-claude-bot
pytest test_main.py -v
```

Expected: 6 tests passed.
