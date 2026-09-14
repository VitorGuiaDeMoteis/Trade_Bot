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
    mode = getattr(request.app.state, "mission_control_mode", "broker")
    if mode == "replay":
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="replay">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "REPLAY LIVE — SIMULAÇÃO HISTÓRICA")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M4 / HISTORICAL REPLAY")
        return HTMLResponse(page, headers=headers)
    elif mode == "night_lab":
        # we keep data-mode="replay" so the javascript parses it correctly without changes
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="replay">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "NIGHT LAB — SIMULAÇÃO EM LOTE")
        page = page.replace("M7 / BROKER OBSERVABILITY / LOCAL DESK", "M8 / NIGHT LAB EXPERIMENT / OLLAMA AI")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M8 / NIGHT LAB EXPERIMENT")
        return HTMLResponse(page, headers=headers)
    return FileResponse(PAGE, media_type="text/html", headers=headers)
