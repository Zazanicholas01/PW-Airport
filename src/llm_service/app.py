import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


REMOTE_PROMPT_URL = "http://10.0.20.68:8000/prompt"
REMOTE_RESPONSE_URL = "http://10.0.20.68:8000/response"
REQUEST_TIMEOUT_SECONDS = 120.0


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt to send to the remote server")


class PromptResponse(BaseModel):
    reply: str
    prompt_url: str
    response_url: str


app = FastAPI(title="LLM Prompt Service", version="1.0.0")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LLM Prompt Service</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4efe6;
      --line: #d3c3a8;
      --text: #1f1a14;
      --muted: #675a4b;
      --accent: #0f6d5f;
      --accent-strong: #0b564b;
      --output: #efe6d6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(circle at top left, #fff7eb 0, transparent 28%),
        linear-gradient(135deg, #f8f3ea 0%, var(--bg) 58%, #e6dccb 100%);
      color: var(--text);
      min-height: 100vh;
    }
    .page {
      width: min(920px, calc(100vw - 32px));
      margin: 32px auto;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: rgba(255, 250, 242, 0.94);
      box-shadow: 0 20px 60px rgba(63, 46, 22, 0.12);
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1.05;
    }
    .meta {
      margin: 0 0 24px;
      color: var(--muted);
      font-size: 15px;
    }
    label {
      display: block;
      margin: 0 0 8px;
      font-weight: 600;
    }
    textarea {
      width: 100%;
      min-height: 240px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      font: inherit;
      color: var(--text);
      background: #fffdf8;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      margin-top: 16px;
      align-items: end;
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 14px 20px;
      font: inherit;
      font-weight: 700;
      color: white;
      background: linear-gradient(180deg, var(--accent) 0%, var(--accent-strong) 100%);
      cursor: pointer;
      min-width: 132px;
    }
    button:disabled {
      opacity: 0.65;
      cursor: wait;
    }
    .status {
      margin: 16px 0 0;
      min-height: 24px;
      color: var(--muted);
    }
    pre {
      margin: 14px 0 0;
      padding: 16px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: var(--output);
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 180px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 14px;
      line-height: 1.5;
    }
    @media (max-width: 720px) {
      .page { margin: 16px auto; padding: 18px; }
      .row { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main class="page">
    <h1>LLM Prompt Service</h1>
    <p class="meta">Sends prompts to <strong>""" + REMOTE_PROMPT_URL + """</strong> and fetches replies from <strong>""" + REMOTE_RESPONSE_URL + """</strong>.</p>

    <label for="prompt">Prompt</label>
    <textarea id="prompt" placeholder="Write the prompt to send to the remote service..."></textarea>

    <div class="row">
      <div></div>
      <button id="send" type="button">Send Prompt</button>
    </div>

    <div id="status" class="status"></div>
    <pre id="output">Response will appear here.</pre>
  </main>

  <script>
    const sendButton = document.getElementById("send");
    const promptInput = document.getElementById("prompt");
    const statusNode = document.getElementById("status");
    const outputNode = document.getElementById("output");

    async function sendPrompt() {
      const prompt = promptInput.value.trim();
      if (!prompt) {
        statusNode.textContent = "Enter a prompt first.";
        promptInput.focus();
        return;
      }

      sendButton.disabled = true;
      statusNode.textContent = "Sending prompt...";
      outputNode.textContent = "";

      try {
        const response = await fetch("/api/prompt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt })
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Request failed");
        }

        statusNode.textContent = "Reply received.";
        outputNode.textContent = data.reply || "";
      } catch (error) {
        statusNode.textContent = "Request failed.";
        outputNode.textContent = error.message || String(error);
      } finally {
        sendButton.disabled = false;
      }
    }

    sendButton.addEventListener("click", sendPrompt);
    promptInput.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        sendPrompt();
      }
    });
  </script>
</body>
</html>"""


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "remote_prompt_url": REMOTE_PROMPT_URL,
        "remote_response_url": REMOTE_RESPONSE_URL,
    }


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


@app.post("/api/prompt", response_model=PromptResponse)
async def prompt(payload: PromptRequest) -> PromptResponse:
    try:
        prompt_data = _post_json(REMOTE_PROMPT_URL, {"prompt": payload.prompt})
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Remote prompt request timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip() or "Remote prompt route returned an error"
        raise HTTPException(status_code=502, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Could not reach remote prompt route") from exc

    response_url = REMOTE_RESPONSE_URL
    request_id = prompt_data.get("request_id")
    if isinstance(request_id, str) and request_id.strip():
        response_url = f"{REMOTE_RESPONSE_URL}?{urlencode({'request_id': request_id})}"

    try:
        response_data = _get_json(response_url)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Remote response request timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip() or "Remote response route returned an error"
        raise HTTPException(status_code=502, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Could not reach remote response route") from exc

    reply = response_data.get("response")
    if not isinstance(reply, str):
        raise HTTPException(status_code=502, detail="Remote response route is missing 'response'")

    return PromptResponse(
        reply=reply,
        prompt_url=REMOTE_PROMPT_URL,
        response_url=response_url,
    )
