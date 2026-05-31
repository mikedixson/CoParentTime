from __future__ import annotations

from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.config import get_ui_config
from app.models import HealthResponse, PlanResultPayload, PlanRunRequest, PlanRunResponse
from app.services.app_service import run_planning
from app.services.ical_exporter import generate_plan_ics


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="CoParenTime MVP", version="0.1.0", lifespan=lifespan)

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
    safe_run_id = run_id.replace("/", "_")[:36]
    filename = f"coparentime-{safe_run_id}.ics"
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    checks = {
        "sqlite_initialized": True,
        "artifacts_writable": True,
    }
    return HealthResponse(status="ok", checks=checks)
