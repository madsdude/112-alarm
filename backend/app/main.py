from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from apscheduler.schedulers.background import BackgroundScheduler

from .repo import init_db, get_session
from .models import GameState, Hospital, Incident, Personnel, Station, Unit
from .services import BASE_GRID_SIZE, dispatch_unit, spawn_incident, tick
from .seed import seed


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="112 Alarm – MVP")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def on_startup():
    init_db()
    seed()
    scheduler = BackgroundScheduler()
    scheduler.add_job(tick, "interval", seconds=10, id="tick")
    scheduler.add_job(spawn_incident, "interval", seconds=45, id="spawn")
    scheduler.start()


def _build_world_state():
    with get_session() as s:
        incidents = s.exec(select(Incident).order_by(Incident.id.desc())).all()
        units = s.exec(select(Unit)).all()
        hospitals = s.exec(select(Hospital)).all()
        stations = s.exec(select(Station)).all()
        personnel = s.exec(select(Personnel)).all()
        gamestate = s.get(GameState, 1)

    active_statuses = {"new", "responding", "resolving"}
    history_statuses = {"resolved", "failed"}

    active_incidents = [inc for inc in incidents if inc.status in active_statuses]
    history_incidents = [inc for inc in incidents if inc.status in history_statuses]
    available_units = [unit for unit in units if unit.status == "available"]
    return {
        "incidents": incidents,
        "units": units,
        "hospitals": hospitals,
        "stations": stations,
        "personnel": personnel,
        "gamestate": gamestate,
        "grid_size": BASE_GRID_SIZE,
        "generated_at": datetime.utcnow(),
        "active_incidents": active_incidents,
        "history_incidents": history_incidents,
        "available_units": available_units,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    ctx = _build_world_state()
    ctx["request"] = request
    return templates.TemplateResponse("index.html", ctx)


def _partial_response(request: Request, template_name: str):
    ctx = _build_world_state()
    ctx["request"] = request
    return templates.TemplateResponse(template_name, ctx)


@app.get("/partials/incidents", response_class=HTMLResponse)
def partial_incidents(request: Request):
    return _partial_response(request, "partials/incidents.html")


@app.get("/partials/units", response_class=HTMLResponse)
def partial_units(request: Request):
    return _partial_response(request, "partials/units.html")


@app.get("/partials/history", response_class=HTMLResponse)
def partial_history(request: Request):
    return _partial_response(request, "partials/history.html")


@app.get("/partials/map", response_class=HTMLResponse)
def partial_map(request: Request):
    return _partial_response(request, "partials/map.html")


@app.get("/partials/personnel", response_class=HTMLResponse)
def partial_personnel(request: Request):
    return _partial_response(request, "partials/personnel.html")


@app.get("/partials/status", response_class=HTMLResponse)
def partial_status(request: Request):
    return _partial_response(request, "partials/status.html")


@app.post("/dispatch", response_class=HTMLResponse)
async def post_dispatch(request: Request, incident_id: int = Form(...), unit_id: int = Form(...)):
    dispatch_unit(incident_id, unit_id)
    if request.headers.get("HX-Request"):
        ctx = _build_world_state()
        ctx["request"] = request
        content = templates.get_template("partials/incidents.html").render(ctx)
        response = HTMLResponse(content)
        response.headers["HX-Trigger"] = "refresh-units,refresh-status,refresh-history,refresh-personnel,refresh-map"
        return response
    return RedirectResponse(url="/", status_code=303)


@app.get("/admin/reset")
def reset():
    seed()
    return RedirectResponse(url="/", status_code=303)

