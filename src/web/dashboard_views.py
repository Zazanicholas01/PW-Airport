import html
from pathlib import Path

from fastapi.responses import HTMLResponse

WEB_DIR = Path(__file__).resolve().parent
DETAIL_TEMPLATE_FILE = WEB_DIR / "templates" / "detail-page.html"


def render_detail_page_from_snapshot(snapshot: dict[str, object]) -> HTMLResponse:
    return render_detail_page(
        title=str(snapshot["title"]),
        subtitle=str(snapshot["subtitle"]),
        fields=list(snapshot["fields"]),
        image_url=str(snapshot["image_url"]),
        image_alt=str(snapshot["image_alt"]),
        progress_percent=int(snapshot["progress_percent"]),
        progress_label=str(snapshot["progress_label"]),
        progress_start_label=str(snapshot["progress_start_label"]),
        progress_end_label=str(snapshot["progress_end_label"]),
        progress_start_unix_ms=snapshot["progress_start_unix_ms"],
        progress_end_unix_ms=snapshot["progress_end_unix_ms"],
        detail_api_path=str(snapshot.get("detail_api_path") or ""),
    )


def _render_detail_field(label: str, value: str, field_key: str | None = None) -> str:
    attr = f' data-field-key="{html.escape(field_key)}"' if field_key else ""
    return (
        f'<div class="detail-field"{attr}>'
        f'<div class="detail-label">{html.escape(label)}</div>'
        f'<div class="detail-value">{html.escape(value)}</div>'
        "</div>"
    )


def _render_fields(fields: list[tuple[str, str] | tuple[str, str, str]]) -> str:
    rendered: list[str] = []

    for field in fields:
        if len(field) == 3:
            label, value, field_key = field
            rendered.append(_render_detail_field(label, value, field_key))
        else:
            label, value = field
            rendered.append(_render_detail_field(label, value))

    return "".join(rendered)


def render_detail_page(
    title: str,
    subtitle: str,
    fields: list[tuple[str, str] | tuple[str, str, str]],
    image_url: str,
    image_alt: str,
    *,
    progress_percent: int = 0,
    progress_label: str = "Tracking unavailable",
    progress_start_label: str = "--:--",
    progress_end_label: str = "--:--",
    progress_start_unix_ms: int | None = None,
    progress_end_unix_ms: int | None = None,
    detail_api_path: str | None = None,
) -> HTMLResponse:
    template = DETAIL_TEMPLATE_FILE.read_text(encoding="utf-8")
    fields_markup = _render_fields(fields)

    html_out = (
        template
        .replace("{{TITLE}}", html.escape(title))
        .replace("{{SUBTITLE}}", html.escape(subtitle))
        .replace("{{FIELDS}}", fields_markup)
        .replace("{{IMAGE_URL}}", html.escape(image_url))
        .replace("{{IMAGE_ALT}}", html.escape(image_alt))
        .replace("{{DETAIL_API_PATH}}", html.escape(detail_api_path or ""))
        .replace("{{PROGRESS_LABEL}}", html.escape(progress_label))
        .replace("{{PROGRESS_PERCENT}}", str(max(0, min(100, progress_percent))))
        .replace("{{PROGRESS_START_LABEL}}", html.escape(progress_start_label))
        .replace("{{PROGRESS_END_LABEL}}", html.escape(progress_end_label))
        .replace("{{PROGRESS_START_UNIX_MS}}", "" if progress_start_unix_ms is None else str(progress_start_unix_ms))
        .replace("{{PROGRESS_END_UNIX_MS}}", "" if progress_end_unix_ms is None else str(progress_end_unix_ms))
    )

    return HTMLResponse(html_out)
