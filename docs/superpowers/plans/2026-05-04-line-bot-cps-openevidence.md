# LINE Bot CPS + OpenEvidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `line-claude-bot/main.py` to use CPS clinical reasoning (via system prompt) and OpenEvidence literature search (via tool_use), deployed on Render with no Mac dependency.

**Architecture:** Single-file FastAPI app. CPS reasoning encoded as a system prompt constant. OpenEvidenceClient class makes cookie-authenticated HTTP calls to openevidence.com. Claude uses tool_use to call `search_evidence` when literature is needed; webhook handler dispatches the call and feeds the result back before the final reply.

**Tech Stack:** Python 3.12, FastAPI, Anthropic SDK (claude-sonnet-4-6), httpx (async), pytest

---

## File Map

| File | Change |
|------|--------|
| `line-claude-bot/main.py` | All changes — new constants, new class, new functions, updated handler |
| `line-claude-bot/test_main.py` | New tests for all new functions; update existing webhook test |

No new files, no new dependencies.

---

### Task 1: Add CPS_SYSTEM_PROMPT and TOOLS constants

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

In `test_main.py`, add at the top (after existing imports):

```python
def test_cps_system_prompt_exists():
    from main import CPS_SYSTEM_PROMPT
    assert isinstance(CPS_SYSTEM_PROMPT, str)
    assert len(CPS_SYSTEM_PROMPT) > 200


def test_tools_definition():
    from main import TOOLS
    assert isinstance(TOOLS, list)
    assert len(TOOLS) == 1
    assert TOOLS[0]["name"] == "search_evidence"
    assert "question" in TOOLS[0]["input_schema"]["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "line-claude-bot" && python -m pytest test_main.py::test_cps_system_prompt_exists test_main.py::test_tools_definition -v
```

Expected: FAIL with `ImportError: cannot import name 'CPS_SYSTEM_PROMPT'`

- [ ] **Step 3: Add CPS_SYSTEM_PROMPT and TOOLS to main.py**

After the `claude = anthropic.Anthropic(...)` line and before `history = ...`, insert:

```python
CPS_SYSTEM_PROMPT = """你是一位內科主治醫師，使用 NEJM Clinical Problem-Solving 格式進行臨床推理。

每次收到病例或臨床問題時，依照以下步驟推理：

## 推理步驟

**步驟 1 — 問題重述**
一句話總結：「這是一位 [年齡][性別]，有 [重要病史]，以 [主訴持續時間] 的 [主訴] 就診，伴隨 [關鍵症狀]。」

**步驟 2 — 鑑別診斷（Top 5–8）**
依預測機率（%）排序。每個診斷標註：
- 預測機率
- 支持證據（來自病例）
- 反對證據
- ⚠️ 標記不可漏診（高死亡率/高致殘率）

必須考慮的不可漏診類別：
- 心血管：ACS、主動脈剝離、肺栓塞、心包填塞
- 神經：蜘蛛膜下腔出血、腦中風、腦膜炎、硬膜外血腫
- 外科急症：AAA破裂、腸穿孔、子宮外孕
- 代謝：敗血症、腎上腺危象、甲狀腺風暴

**步驟 3 — 關鍵鑑別點**
針對最可能的 2–3 個診斷，列出能推高或降低機率的關鍵發現，附 LR+/LR−（已知時）。

LR 解讀：
- LR+ > 10 或 LR− < 0.1：強力改變機率
- LR+ 5–10 或 LR− 0.1–0.2：中度改變
- LR+ 2–5 或 LR− 0.2–0.5：輕度改變

**步驟 4 — 文獻查詢（工具呼叫）**
以下情況呼叫 search_evidence 工具：
- 罕見診斷需要最新指引
- 兩個診斷機率相近，文獻有助區分
- 需要具體治療方案或藥物劑量
- 搜尋問題請用英文以獲得最佳結果

**步驟 5 — Bayesian 更新**（若有呼叫 search_evidence）
使用文獻資料重新計算後驗機率：
後驗勝算 = 先驗勝算 × LR
後驗機率 = 後驗勝算 / (1 + 後驗勝算)

**步驟 6 — 結論**
- 最可能診斷（附最終機率）
- 建議檢查（依優先順序）
- 緊急處置（若有急症）

## 輸出規範
- 語言：繁體中文
- 格式：清楚分節標題
- 包含 LR+/LR− 數值（已知時）
- 無論機率高低，⚠️ 不可漏診診斷必須列出
- 若問題非臨床病例（一般對話），正常回覆即可，不需套用推理框架"""

TOOLS = [
    {
        "name": "search_evidence",
        "description": "Search OpenEvidence for medical literature. Use for rare diagnoses needing current guidelines, close-probability differentials, or specific treatment protocols.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Clinical question in English (e.g., 'likelihood ratio of S3 gallop for heart failure')",
                }
            },
            "required": ["question"],
        },
    }
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_main.py::test_cps_system_prompt_exists test_main.py::test_tools_definition -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add CPS system prompt and tool definition"
```

---

### Task 2: Add OpenEvidenceClient class

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
def test_oe_client_no_cookies():
    """ask() returns fallback string when OE_COOKIES_JSON is not set."""
    import asyncio
    with patch.dict("os.environ", {}, clear=False):
        # Remove OE_COOKIES_JSON if present
        import os
        os.environ.pop("OE_COOKIES_JSON", None)
        # Re-import to get fresh instance
        import importlib
        import main as m
        importlib.reload(m)
        result = asyncio.get_event_loop().run_until_complete(m.oe_client.ask("test"))
    assert result == "[文獻搜尋未設定，缺少 OE_COOKIES_JSON]"


def test_oe_client_extract_text_raw():
    from main import OpenEvidenceClient
    client = OpenEvidenceClient.__new__(OpenEvidenceClient)
    article = {"output": {"structured_article": {"raw_text": "hello evidence"}}}
    assert client._extract_text(article) == "hello evidence"


def test_oe_client_extract_text_fallback():
    from main import OpenEvidenceClient
    client = OpenEvidenceClient.__new__(OpenEvidenceClient)
    article = {"output": {"text": "fallback text"}}
    assert client._extract_text(article) == "fallback text"


def test_oe_client_extract_text_empty():
    from main import OpenEvidenceClient
    client = OpenEvidenceClient.__new__(OpenEvidenceClient)
    article = {"output": {}}
    assert client._extract_text(article) == "[文獻搜尋無結果]"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest test_main.py::test_oe_client_no_cookies test_main.py::test_oe_client_extract_text_raw test_main.py::test_oe_client_extract_text_fallback test_main.py::test_oe_client_extract_text_empty -v
```

Expected: FAIL with `ImportError: cannot import name 'OpenEvidenceClient'`

- [ ] **Step 3: Add OpenEvidenceClient and _blocks_to_dicts to main.py**

Add `import asyncio` and `import time` to the imports at the top.

After the `TOOLS` constant, add:

```python
def _blocks_to_dicts(content) -> list[dict]:
    """Serialize Anthropic SDK content blocks to plain dicts for history storage."""
    result = []
    for block in content:
        if block.type == "tool_use":
            result.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        elif block.type == "text":
            result.append({"type": "text", "text": block.text})
    return result


class OpenEvidenceClient:
    BASE_URL = "https://www.openevidence.com"
    PENDING = {"queued", "pending", "processing", "running", "in_progress"}

    def __init__(self):
        raw = os.environ.get("OE_COOKIES_JSON", "")
        if not raw:
            self._cookie_header = None
            return
        cookies = json.loads(raw)
        pairs = [
            f"{c['name']}={c['value']}"
            for c in cookies
            if "openevidence.com" in c.get("domain", "")
        ]
        self._cookie_header = "; ".join(pairs) if pairs else None

    def _headers(self) -> dict:
        return {
            "cookie": self._cookie_header or "",
            "origin": self.BASE_URL,
            "referer": f"{self.BASE_URL}/",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    async def ask(self, question: str) -> str:
        if not self._cookie_header:
            return "[文獻搜尋未設定，缺少 OE_COOKIES_JSON]"

        payload = {
            "article_type": "Ask OpenEvidence Light with citations",
            "inputs": {
                "variant_configuration_file": "prod",
                "attachments": [],
                "question": question,
                "use_gatekeeper": True,
            },
            "personalization_enabled": False,
            "disable_caching": False,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/api/article", headers=self._headers(), json=payload
            )
            if resp.status_code == 401:
                return "[文獻搜尋暫時無法使用，請更新 Cookies]"
            resp.raise_for_status()
            article_id = resp.json()["id"]

        started = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                if asyncio.get_event_loop().time() - started > 45:
                    return "[文獻搜尋逾時]"
                resp = await client.get(
                    f"{self.BASE_URL}/api/article/{article_id}", headers=self._headers()
                )
                if resp.status_code == 401:
                    return "[文獻搜尋暫時無法使用，請更新 Cookies]"
                article = resp.json()
                status = str(article.get("status", "")).lower()
                if status and status not in self.PENDING:
                    return self._extract_text(article)
                await asyncio.sleep(3)

    def _extract_text(self, article: dict) -> str:
        output = article.get("output") or {}
        structured = output.get("structured_article") or {}
        raw_text = structured.get("raw_text", "")
        if raw_text:
            return raw_text
        return output.get("text") or "[文獻搜尋無結果]"


oe_client = OpenEvidenceClient()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_main.py::test_oe_client_no_cookies test_main.py::test_oe_client_extract_text_raw test_main.py::test_oe_client_extract_text_fallback test_main.py::test_oe_client_extract_text_empty -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add OpenEvidenceClient with cookie auth and async polling"
```

---

### Task 3: Add split_message() utility

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
def test_split_message_short():
    from main import split_message
    result = split_message("hello")
    assert result == ["hello"]


def test_split_message_splits_on_paragraphs():
    from main import split_message
    # Build text > 4800 chars using paragraph breaks
    para = "A" * 1000
    text = "\n\n".join([para] * 6)  # 6000 chars with separators
    result = split_message(text, limit=4800)
    assert len(result) > 1
    assert all(len(chunk) <= 4800 for chunk in result)


def test_split_message_caps_at_five():
    from main import split_message
    # 30 paragraphs of 1000 chars each
    text = "\n\n".join(["B" * 1000] * 30)
    result = split_message(text, limit=4800)
    assert len(result) <= 5


def test_split_message_empty():
    from main import split_message
    assert split_message("") == [""]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest test_main.py::test_split_message_short test_main.py::test_split_message_splits_on_paragraphs test_main.py::test_split_message_caps_at_five test_main.py::test_split_message_empty -v
```

Expected: FAIL with `ImportError: cannot import name 'split_message'`

- [ ] **Step 3: Add split_message to main.py**

After the `oe_client = OpenEvidenceClient()` line, add:

```python
def split_message(text: str, limit: int = 4800) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for para in text.split("\n\n"):
        if not current:
            current = para[:limit]
        elif len(current) + 2 + len(para) <= limit:
            current += "\n\n" + para
        else:
            chunks.append(current)
            if len(chunks) == 4:
                chunks.append(para[:limit])
                return chunks
            current = para[:limit]

    if current:
        chunks.append(current)

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_main.py::test_split_message_short test_main.py::test_split_message_splits_on_paragraphs test_main.py::test_split_message_caps_at_five test_main.py::test_split_message_empty -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add split_message for LINE 5-message limit"
```

---

### Task 4: Add call_claude() with tool_use handling

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
def test_call_claude_no_tool_use():
    """call_claude returns text and unchanged history when no tool is triggered."""
    import asyncio
    from unittest.mock import MagicMock, patch

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "診斷結果"

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [mock_text_block]

    messages = [{"role": "user", "content": "咳嗽三天"}]

    with patch("main.claude.messages.create", return_value=mock_response):
        from main import call_claude
        text, updated = asyncio.get_event_loop().run_until_complete(
            call_claude(messages)
        )

    assert text == "診斷結果"
    assert updated == messages  # unchanged — no tool messages added


def test_call_claude_with_tool_use():
    """call_claude executes tool, appends tool messages, returns second response text."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    # First response: tool_use
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "tu_123"
    mock_tool_block.name = "search_evidence"
    mock_tool_block.input = {"question": "S3 gallop LR for heart failure"}

    mock_resp1 = MagicMock()
    mock_resp1.stop_reason = "tool_use"
    mock_resp1.content = [mock_tool_block]

    # Second response: final text
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "根據文獻，最可能診斷為 CHF"

    mock_resp2 = MagicMock()
    mock_resp2.stop_reason = "end_turn"
    mock_resp2.content = [mock_text_block]

    messages = [{"role": "user", "content": "病患有 S3 gallop"}]

    with patch("main.claude.messages.create", side_effect=[mock_resp1, mock_resp2]), \
         patch("main.oe_client.ask", new=AsyncMock(return_value="S3 gallop LR+ 11.0 for CHF")):
        from main import call_claude
        text, updated = asyncio.get_event_loop().run_until_complete(
            call_claude(messages)
        )

    assert text == "根據文獻，最可能診斷為 CHF"
    # updated should have 3 entries: original user msg + assistant tool_use + user tool_result
    assert len(updated) == 3
    assert updated[1]["role"] == "assistant"
    assert updated[2]["role"] == "user"
    assert updated[2]["content"][0]["type"] == "tool_result"
    assert updated[2]["content"][0]["content"] == "S3 gallop LR+ 11.0 for CHF"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest test_main.py::test_call_claude_no_tool_use test_main.py::test_call_claude_with_tool_use -v
```

Expected: FAIL with `ImportError: cannot import name 'call_claude'`

- [ ] **Step 3: Add call_claude to main.py**

After `split_message`, add:

```python
async def call_claude(user_history: list[dict]) -> tuple[str, list[dict]]:
    """Call Claude with CPS system prompt. Handles one tool_use round if triggered.

    Returns (final_text, updated_history).
    updated_history includes any tool_use/tool_result messages inserted mid-turn.
    """
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=CPS_SYSTEM_PROMPT,
        tools=TOOLS,
        messages=user_history,
    )

    if response.stop_reason != "tool_use":
        return response.content[0].text, user_history

    tool_block = next(b for b in response.content if b.type == "tool_use")
    evidence = await oe_client.ask(tool_block.input["question"])

    extended = user_history + [
        {"role": "assistant", "content": _blocks_to_dicts(response.content)},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_block.id, "content": evidence}
            ],
        },
    ]

    response2 = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=CPS_SYSTEM_PROMPT,
        tools=TOOLS,
        messages=extended,
    )
    return response2.content[0].text, extended
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_main.py::test_call_claude_no_tool_use test_main.py::test_call_claude_with_tool_use -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: add call_claude with tool_use and OpenEvidence dispatch"
```

---

### Task 5: Update add_message, send_reply, and webhook handler

**Files:**
- Modify: `line-claude-bot/main.py`
- Modify: `line-claude-bot/test_main.py`

- [ ] **Step 1: Update the existing webhook test**

In `test_main.py`, replace `test_webhook_valid_returns_ok` with:

```python
def test_webhook_valid_returns_ok():
    from main import app, history
    history.clear()
    body = make_line_body("Uabc", "hello")
    sig = make_sig(body)

    with patch("main.LINE_CHANNEL_SECRET", FAKE_SECRET), \
         patch("main.call_claude", new=AsyncMock(return_value=("Hi there!", []))), \
         patch("main.send_reply", new=AsyncMock()):
        from main import app
        client = TestClient(app)
        response = client.post("/webhook", content=body, headers={"X-Line-Signature": sig})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

Also add a test for multi-message send_reply:

```python
def test_send_reply_multi_message():
    """send_reply sends all chunks as separate LINE messages."""
    import asyncio

    async def run():
        with patch("main.LINE_CHANNEL_ACCESS_TOKEN", "tok"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_post = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            from main import send_reply
            await send_reply("reply_token_abc", ["chunk1", "chunk2"])
            call_kwargs = mock_post.call_args
            messages = call_kwargs.kwargs["json"]["messages"]
            assert len(messages) == 2
            assert messages[0]["text"] == "chunk1"
            assert messages[1]["text"] == "chunk2"

    asyncio.get_event_loop().run_until_complete(run())
```

- [ ] **Step 2: Run tests to confirm they fail (expected — functions not updated yet)**

```bash
python -m pytest test_main.py::test_webhook_valid_returns_ok test_main.py::test_send_reply_multi_message -v
```

Expected: FAIL

- [ ] **Step 3: Update add_message, send_reply, and webhook in main.py**

**Replace** the existing `add_message` function:

```python
def add_message(user_id: str, role: str, content: str | list) -> None:
    history[user_id].append({"role": role, "content": content})
    if len(history[user_id]) > MAX_HISTORY:
        history[user_id] = history[user_id][-MAX_HISTORY:]
```

**Replace** the existing `send_reply` function:

```python
async def send_reply(reply_token: str, messages: list[str]) -> None:
    async with httpx.AsyncClient() as http:
        await http.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": m} for m in messages],
            },
            timeout=10.0,
        )
```

**Replace** the `webhook` function body (the for-loop section):

```python
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

        text, extended = await call_claude(list(history[user_id]))

        # Sync history with any tool_use/tool_result messages inserted mid-turn
        history[user_id] = extended
        add_message(user_id, "assistant", text)

        await send_reply(reply_token, split_message(text))

    return JSONResponse(content={"status": "ok"})
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest test_main.py -v
```

Expected: all PASS (verify_signature, add_message, history, webhook, send_reply, split_message, oe_client, call_claude tests)

- [ ] **Step 5: Commit**

```bash
git add line-claude-bot/main.py line-claude-bot/test_main.py
git commit -m "feat: wire CPS+OE into webhook handler, multi-message reply"
```

---

### Task 6: Deploy to Render

**Files:** None (Render dashboard + git push)

- [ ] **Step 1: Export OpenEvidence cookies**

On your Mac:

```bash
python ~/openevidence-mcp/extract_chrome_cookies.py
```

Copy the full JSON output (the entire array `[{...}, ...]`).

- [ ] **Step 2: Set environment variables in Render dashboard**

Go to your Render service → Environment → Add/update:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `OE_COOKIES_JSON` | The JSON array from Step 1 (paste as-is) |

`LINE_CHANNEL_ACCESS_TOKEN` and `LINE_CHANNEL_SECRET` should already be set from before.

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```

Render auto-deploys on push. Watch the deploy logs in the Render dashboard.

- [ ] **Step 4: Smoke test — basic reply**

Send a LINE message: `你好`

Expected: Claude replies in Traditional Chinese (no CPS reasoning triggered for non-clinical messages).

- [ ] **Step 5: Smoke test — clinical case**

Send a LINE message:
```
45歲男性，突發胸痛2小時，向左肩放射，冒冷汗，ECG有ST elevation in II, III, aVF
```

Expected within ~30s:
- Structured DDx with probabilities
- ⚠️ ACS listed as must-not-miss
- LR values where applicable
- Possible search_evidence call (if OE responds in time)

- [ ] **Step 6: Verify OE integration**

Send a LINE message:
```
請查詢 Wells score for PE 的臨床應用
```

Expected: Claude calls search_evidence, cites OpenEvidence literature in the reply. If cookies are expired, reply should include `[文獻搜尋暫時無法使用，請更新 Cookies]` but still give a text answer.
