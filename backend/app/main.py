from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from apscheduler.schedulers.background import BackgroundScheduler

from .repo import init_db, get_session
from .models import Incident, Unit
from .services import spawn_incident, dispatch_unit, tick
from .seed import seed

app = FastAPI(title="112 Alarm – MVP")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup():
    init_db()
    seed()
    scheduler = BackgroundScheduler()
    scheduler.add_job(tick, "interval", seconds=10, id="tick")
    scheduler.add_job(spawn_incident, "interval", seconds=45, id="spawn")
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with get_session() as s:
        incidents = s.exec(select(Incident).order_by(Incident.id.desc())).all()
        units = s.exec(select(Unit)).all()

    active_statuses = {"new", "responding", "resolving"}
    history_statuses = {"resolved", "failed"}

    active_incidents = [inc for inc in incidents if inc.status in active_statuses]
    history_incidents = [inc for inc in incidents if inc.status in history_statuses]
    available_units = [unit for unit in units if unit.status == "available"]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "incidents": incidents,
            "units": units,
            "active_incidents": active_incidents,
            "history_incidents": history_incidents,
            "available_units": available_units,
        },
    )


@app.post("/dispatch")
def post_dispatch(incident_id: int = Form(...), unit_id: int = Form(...)):
    dispatch_unit(incident_id, unit_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/admin/reset")
def reset():
    seed()
    return RedirectResponse(url="/", status_code=303)

