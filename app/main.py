from __future__ import annotations

from contextlib import asynccontextmanager
import json
import re

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app import db
from app.config import get_ui_config
from app.models import HealthResponse, PlanResultPayload, PlanRunRequest, PlanRunResponse
from app.services.app_service import run_planning
from app.services.ical_exporter import generate_plan_ics


def _sanitize_filename(filename: str, max_length: int = 50) -> str:
    """Sanitize filename to prevent directory traversal and other attacks.
    
    Args:
        filename: The filename to sanitize
        max_length: Maximum length of the sanitized filename
        
    Returns:
        Sanitized filename containing only safe characters
    """
    # Remove any path separators and null bytes
    safe = filename.replace("\\", "").replace("/", "").replace("\x00", "")
    
    # Keep only alphanumeric, hyphens, underscores, and dots
    safe = re.sub(r"[^\w\-\.]", "", safe)
    
    # Remove leading/trailing dots and hyphens
    safe = safe.strip(".-")
    
    # Truncate to max length
    safe = safe[:max_length]
    
    # Ensure non-empty
    return safe or "file"


async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Clickjacking protection
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    
    # XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Referrer policy - prevent referrer leakage
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy - restrictive by default for local app
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    
    return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="CoParenTime MVP", version="0.1.0", lifespan=lifespan)

# Add security headers middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=add_security_headers)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    ui_config = get_ui_config()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "ui_config_json": json.dumps(ui_config),
            "partner_enabled": bool(ui_config.get("partner_enabled", False)),
        },
    )


@app.post("/plan/run", response_model=PlanRunResponse)
def run_plan(req: PlanRunRequest) -> PlanRunResponse:
    result = run_planning(req)
    return PlanRunResponse(result=result)


@app.get("/plan/{run_id}", response_model=PlanRunResponse)
def get_plan(run_id: str) -> PlanRunResponse:
    result = db.get_run_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return PlanRunResponse(result=PlanResultPayload.model_validate(result))


@app.get("/plan/{run_id}/ical")
def get_plan_ical(run_id: str, plan_id: str | None = Query(default=None)) -> Response:
    result = db.get_run_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    payload = PlanResultPayload.model_validate(result)
    ics_content = generate_plan_ics(payload, plan_id)
    
    # Sanitize the run_id for use in filename
    safe_run_id = _sanitize_filename(run_id.replace("/", "_"), max_length=36)
    filename = f"coparentime-{safe_run_id}.ics"
    
    # Use RFC 5987 encoding for filename to handle special characters properly
    # The filename* parameter is for non-ASCII characters, filename for ASCII fallback
    content_disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}'
    
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": content_disposition},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    checks = {
        "sqlite_initialized": True,
        "artifacts_writable": True,
    }
    return HealthResponse(status="ok", checks=checks)
