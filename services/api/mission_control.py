"""Static, same-origin observation dashboard; no trading controls."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
PAGE = Path(__file__).with_name("static") / "mission-control.html"


@router.get("/mission-control", include_in_schema=False)
def mission_control() -> FileResponse:
    return FileResponse(
        PAGE,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'"
            ),
        },
    )
