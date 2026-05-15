import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


REMOTE_PROMPT_URL = "http://10.0.20.84:8000/api/prompt"
REMOTE_RESPONSE_URL = "http://10.0.20.84:8000/api/response"
REQUEST_TIMEOUT_SECONDS = 120.0
REMOTE_STREAM = True
SERVICE_DIR = Path(__file__).resolve().parent
STATIC_DIR = SERVICE_DIR / "static"
TEMPLATE_DIR = SERVICE_DIR / "templates"
IMG_DIR = SERVICE_DIR / "img"
INDEX_FILE = TEMPLATE_DIR / "index.html"


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt to send to the remote server")


class PromptResponse(BaseModel):
    reply: str
    prompt_url: str
    response_url: str | None


app = FastAPI(title="LLM Prompt Service", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/img", StaticFiles(directory=str(IMG_DIR)), name="img")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE, media_type="text/html")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "remote_prompt_url": REMOTE_PROMPT_URL,
        "remote_response_url": REMOTE_RESPONSE_URL,
        "remote_stream": REMOTE_STREAM,
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


def _post_streaming_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        chunks: list[str] = []
        last_object: dict[str, object] | None = None

        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                try:
                    return json.loads(line)
                except json.JSONDecodeError as exc:
                    raise HTTPException(status_code=502, detail="Remote stream returned invalid JSON") from exc

            if not isinstance(item, dict):
                continue

            piece = _extract_reply(item)
            if piece:
                chunks.append(piece)
            elif isinstance(item.get("message"), dict):
                content = item["message"].get("content")
                if isinstance(content, str) and content:
                    chunks.append(content)
            elif isinstance(item.get("delta"), dict):
                content = item["delta"].get("content")
                if isinstance(content, str) and content:
                    chunks.append(content)

            last_object = item

        if last_object is None:
            raise HTTPException(status_code=502, detail="Remote stream returned no data")

        result = dict(last_object)
        if chunks:
            result["response"] = "".join(chunks)
        return result


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_reply(data: dict[str, object]) -> str | None:
    for key in ("response", "reply", "answer", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


@app.post("/api/prompt", response_model=PromptResponse)
async def prompt(payload: PromptRequest) -> PromptResponse:
    try:
        request_payload: dict[str, object] = {"question": payload.prompt}
        prompt_data = (
            _post_streaming_json(REMOTE_PROMPT_URL, {**request_payload, "stream": True})
            if REMOTE_STREAM
            else _post_json(REMOTE_PROMPT_URL, request_payload)
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Remote prompt request timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip() or "Remote prompt route returned an error"
        raise HTTPException(status_code=502, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Could not reach remote prompt route") from exc

    direct_reply = _extract_reply(prompt_data)
    if direct_reply is not None:
        return PromptResponse(
            reply=direct_reply,
            prompt_url=REMOTE_PROMPT_URL,
            response_url=None,
        )

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

    reply = _extract_reply(response_data)
    if reply is None:
        raise HTTPException(status_code=502, detail="Remote response route is missing a text reply")

    return PromptResponse(
        reply=reply,
        prompt_url=REMOTE_PROMPT_URL,
        response_url=response_url,
    )
