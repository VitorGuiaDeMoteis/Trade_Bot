"""Static, same-origin observation dashboard; no trading controls."""

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()
PAGE = Path(__file__).with_name("static") / "mission-control.html"


@router.get("/mission-control", include_in_schema=False)
def mission_control(request: Request) -> Response:
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        ),
    }
    if getattr(request.app.state, "mission_control_mode", "broker") == "replay":
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="replay">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "REPLAY LIVE — SIMULAÇÃO HISTÓRICA")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M4 / HISTORICAL REPLAY")
        return HTMLResponse(page, headers=headers)
    return FileResponse(PAGE, media_type="text/html", headers=headers)
