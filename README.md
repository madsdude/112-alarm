# 112 Alarm – TORN-style browsergame (TORN-inspireret tekststil)

Enkelt, tekst-/UI-lettet dispatch-spil hvor du driver en 112-central: opret brandstationer og hospitaler, ansæt mandskab, tildel køretøjer og håndtér indsatser. Minimal klik-UI (TORN-agtig), hurtig server-renderet webapp.

---

## 🚀 Hurtigt overblik

* **Genre**: Management/dispatch (tekst-first, minimal grafik)
* **Loop**: Systemet genererer hændelser → du dispatcher enheder → hændelser løses → du får XP/penge → udbyg stationer/hospitaler.
* **MVP mål (uge 1)**:

  1. Opret stationer, hospitaler, enheder, personale (seed-data).
  2. Auto-generér hændelser hvert 30.–60. sekund (sværhedsgrad, kravniveau).
  3. UI-liste: åbne hændelser + ledige enheder. Knap til at **dispatch**.
  4. Simpel løsningslogik (kræver X brand + Y ambulance). Belønning ved løsning.
* **Stack (anbefalet)**: FastAPI + Jinja2 + HTMX (intet SPA-framework), SQLite (MVP), APScheduler til “ticks”.
* **Kør**: `docker compose up --build` (se filerne nedenfor).

---

## 📦 Projektstruktur

```
112-alarm/
├─ docker-compose.yml
├─ backend/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app/
│     ├─ main.py
│     ├─ models.py
│     ├─ repo.py
│     ├─ services.py
│     ├─ seed.py
│     ├─ templates/
│     │  ├─ base.html
│     │  └─ index.html
│     └─ static/
│        └─ styles.css  (valgfri; vi bruger Tailwind CDN for nemhed)
└─ README.md
```

---

## 🧩 Datamodel (MVP)

**Station**(id, name, city)

**Hospital**(id, name, city, capacity, occupied)

**Unit**(id, kind["fire","ambulance","police"], name, status["available","enroute","at_scene","returning"], station_id)

**Incident**(id, type["fire","medical","traffic"], severity[1..5], city, status["new","responding","resolving","resolved","failed"], need_fire, need_ambulance, created_at, deadline_s)

**Dispatch**(id, incident_id, unit_id, assigned_at)

> Simpelt: Kravfeltet er `need_fire` og `need_ambulance`. Når dispatch >= krav → status går til `resolving` og efter kort varighed til `resolved`.

---

## 🌐 API/Views (MVP)

* `GET /` – Dashboard med hændelser og enheder (server-renderet HTML)
* `POST /dispatch` – Tildel enhed til hændelse (HTMX form)
* `POST /resolve-tick` – (intern) service kaldes af scheduler til at opdatere status
* `GET /admin/reset` – Nulstil/seed demo-data (dev)

---

## 🧠 Spil/tick logik (forenklet)

* Hvert 30–60s: skab 1 ny hændelse i en tilfældig by (fra stations/hospitals byer).
* Hvert 10s:

  * Hændelser `responding`→`resolving` hvis krav opfyldt.
  * `resolving`→`resolved` efter kort varighed; frigiv enheder (status `returning`→`available`).
  * Hvis `deadline_s` passeres og krav ikke opfyldt → `failed` (straf/minus-score).

---

## 🔧 Docker & appfiler

### docker-compose.yml

```yaml
version: "3.9"
services:
  game:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - TZ=Europe/Copenhagen
    volumes:
      - ./backend/app:/app/app  # hot-reload udvikling
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### backend/Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PYTHONUNBUFFERED=1
```

### backend/requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlmodel==0.0.22
jinja2==3.1.4
pydantic-settings==2.5.2
apscheduler==3.10.4
python-multipart==0.0.9
```

---

## 🗂️ Backend kode

### app/models.py

```python
from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class Station(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str

class Hospital(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str
    capacity: int = 10
    occupied: int = 0

class Unit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str  # "fire" | "ambulance" | "police"
    name: str
    status: str = "available"  # available, enroute, at_scene, returning
    station_id: Optional[int] = Field(default=None, foreign_key="station.id")

class Incident(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str  # fire | medical | traffic
    severity: int  # 1..5
    city: str
    status: str = "new"  # new, responding, resolving, resolved, failed
    need_fire: int = 0
    need_ambulance: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deadline_s: int = 180

class Dispatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: int = Field(foreign_key="incident.id")
    unit_id: int = Field(foreign_key="unit.id")
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
```

### app/repo.py

```python
from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine

gine = create_engine("sqlite:///./game.db", echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
```

### app/services.py

```python
import random
from datetime import datetime, timedelta
from sqlmodel import select
from .models import Station, Hospital, Unit, Incident, Dispatch
from .repo import get_session

CITIES_FALLBACK = ["Randers", "Aarhus", "Viborg", "Silkeborg", "Aalborg"]

INCIDENT_TYPES = [
    ("fire",  {"fire": (1, 3), "ambulance": (0, 1)}),
    ("medical", {"fire": (0, 1), "ambulance": (1, 2)}),
    ("traffic", {"fire": (0, 1), "ambulance": (1, 2)}),
]

def random_city(session):
    cities = [s.city for s in session.exec(select(Station)).all()] or CITIES_FALLBACK
    return random.choice(cities)

def spawn_incident():
    with get_session() as s:
        typ, req = random.choice(INCIDENT_TYPES)
        inc = Incident(
            type=typ,
            severity=random.randint(1, 5),
            city=random_city(s),
            need_fire=random.randint(*req["fire"]),
            need_ambulance=random.randint(*req["ambulance"]),
            deadline_s=random.choice([180, 240, 300])
        )
        s.add(inc)
        s.commit()
        s.refresh(inc)
        return inc

def dispatch_unit(incident_id: int, unit_id: int) -> bool:
    with get_session() as s:
        inc = s.get(Incident, incident_id)
        unit = s.get(Unit, unit_id)
        if not inc or not unit: return False
        if unit.status != "available": return False
        # Assign
        unit.status = "enroute"
        s.add(Dispatch(incident_id=inc.id, unit_id=unit.id))
        if inc.status == "new":
            inc.status = "responding"
        s.add(unit); s.add(inc); s.commit()
        return True

def tick():
    now = datetime.utcnow()
    with get_session() as s:
        incidents = s.exec(select(Incident).where(Incident.status.in_(["new","responding","resolving"])) ).all()
        # Move responding -> resolving if enough units present
        for inc in incidents:
            if inc.status in ("new","responding"):
                # Count dispatched
                d = s.exec(select(Dispatch).where(Dispatch.incident_id==inc.id)).all()
                fire_count = 0
                amb_count = 0
                for di in d:
                    u = s.get(Unit, di.unit_id)
                    if u.kind == "fire": fire_count += 1
                    if u.kind == "ambulance": amb_count += 1
                if fire_count >= inc.need_fire and amb_count >= inc.need_ambulance:
                    inc.status = "resolving"
            elif inc.status == "resolving":
                # simple resolve window based on severity
                age = (now - inc.created_at).total_seconds()
                if age > 60 + 20*inc.severity:
                    inc.status = "resolved"
                    # free units
                    for di in s.exec(select(Dispatch).where(Dispatch.incident_id==inc.id)):
                        u = s.get(Unit, di.unit_id)
                        if u:
                            u.status = "returning"
                            s.add(u)
        # Move returning -> available
        for u in s.exec(select(Unit).where(Unit.status=="returning")):
            u.status = "available"
            s.add(u)
        # Fail overdue
        for inc in s.exec(select(Incident).where(Incident.status.in_(["new","responding"])) ):
            age = (now - inc.created_at).total_seconds()
            if age > inc.deadline_s:
                inc.status = "failed"
                # (Optionelt: straf)
                s.add(inc)
        s.commit()
```

### app/seed.py

```python
from sqlmodel import select
from .models import Station, Hospital, Unit
from .repo import get_session

def seed():
    with get_session() as s:
        if s.exec(select(Station)).first():
            return  # already seeded
        stations = [
            Station(name="Station Randers", city="Randers"),
            Station(name="Station Aarhus", city="Aarhus"),
        ]
        hospitals = [
            Hospital(name="Randers Hospital", city="Randers", capacity=20),
            Hospital(name="Aarhus Hospital", city="Aarhus", capacity=40),
        ]
        units = [
            Unit(kind="fire", name="BR-1", station_id=1),
            Unit(kind="fire", name="BR-2", station_id=1),
            Unit(kind="ambulance", name="AMB-1", station_id=1),
            Unit(kind="ambulance", name="AMB-2", station_id=2),
            Unit(kind="police", name="POL-1", station_id=2),
        ]
        for x in stations + hospitals + units:
            s.add(x)
        s.commit()
```

### app/main.py

```python
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from apscheduler.schedulers.background import BackgroundScheduler
from .repo import init_db, get_session
from .models import Station, Hospital, Unit, Incident, Dispatch
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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "incidents": incidents,
        "units": units,
    })

@app.post("/dispatch")
def post_dispatch(incident_id: int = Form(...), unit_id: int = Form(...)):
    ok = dispatch_unit(incident_id, unit_id)
    # Simpelt redirect; kunne være HTMX partial
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/reset")
def reset():
    seed()  # idempotent
    return RedirectResponse(url="/", status_code=303)
```

### app/templates/base.html

```html
<!doctype html>
<html lang="da">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>112 Alarm – MVP</title>
  <script src="https://unpkg.com/htmx.org@1.9.12" defer></script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  <div class="max-w-6xl mx-auto p-4">
    <header class="mb-4 flex items-center justify-between">
      <h1 class="text-2xl font-bold">112 Alarm <span class="text-sky-400">(MVP)</span></h1>
      <nav class="text-sm opacity-80">TORN-style UI • FastAPI • HTMX</nav>
    </header>
    <main>
      {% block content %}{% endblock %}
    </main>
  </div>
</body>
</html>
```

### app/templates/index.html

```html
{% extends "base.html" %}
{% block content %}
<div class="grid md:grid-cols-2 gap-4">
  <section class="bg-slate-900/60 rounded-xl p-4">
    <h2 class="font-semibold mb-2">Åbne hændelser</h2>
    <div class="space-y-2">
      {% for inc in incidents if inc.status in ["new","responding","resolving"] %}
        <div class="p-3 rounded-lg bg-slate-800/70">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm uppercase tracking-wide opacity-70">#{{ inc.id }} • {{ inc.city }}</div>
              <div class="text-base">
                <span class="font-semibold">{{ inc.type|capitalize }}</span>
                <span class="ml-2 text-xs opacity-70">Sværhedsgrad: {{ inc.severity }}</span>
                <span class="ml-2 text-xs">Status: <span class="text-sky-300">{{ inc.status }}</span></span>
              </div>
              <div class="text-xs mt-1 opacity-80">Krav – Brand: {{ inc.need_fire }}, Ambulance: {{ inc.need_ambulance }}</div>
            </div>
            <form method="post" action="/dispatch" class="flex items-center gap-2">
              <input type="hidden" name="incident_id" value="{{ inc.id }}" />
              <select name="unit_id" class="bg-slate-900 rounded px-2 py-1 text-sm">
                {% for u in units if u.status == 'available' %}
                  <option value="{{ u.id }}">{{ u.name }} ({{ u.kind }})</option>
                {% endfor %}
              </select>
              <button class="px-3 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-sm">Dispatch</button>
            </form>
          </div>
        </div>
      {% else %}
        <div class="text-sm opacity-80">Ingen åbne hændelser lige nu.</div>
      {% endfor %}
    </div>
  </section>

  <section class="bg-slate-900/60 rounded-xl p-4">
    <h2 class="font-semibold mb-2">Enheder</h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {% for u in units %}
        <div class="p-3 rounded-lg bg-slate-800/70">
          <div class="text-sm uppercase opacity-70">{{ u.name }}</div>
          <div class="text-base">Type: <span class="font-semibold">{{ u.kind }}</span></div>
          <div class="text-xs mt-1">Status: <span class="text-emerald-300">{{ u.status }}</span></div>
        </div>
      {% endfor %}
    </div>
  </section>
</div>

<section class="mt-4 grid md:grid-cols-2 gap-4">
  <div class="bg-slate-900/60 rounded-xl p-4">
    <h3 class="font-semibold mb-2">Historik</h3>
    <ul class="text-sm space-y-1">
      {% for inc in incidents if inc.status in ["resolved","failed"] %}
        <li class="opacity-90">#{{ inc.id }} – {{ inc.type }} i {{ inc.city }} → <span class="{% if inc.status=='resolved' %}text-emerald-400{% else %}text-rose-400{% endif %}">{{ inc.status }}</span></li>
      {% else %}
        <li class="opacity-70">Ingen historik endnu.</li>
      {% endfor %}
    </ul>
  </div>
  <div class="bg-slate-900/60 rounded-xl p-4">
    <h3 class="font-semibold mb-2">Dev</h3>
    <a href="/admin/reset" class="inline-block px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm">Reset/seed</a>
    <p class="text-xs opacity-70 mt-2">Hændelser spawner automatisk ca. hver 45s. Systemet tjekker status hvert 10s.</p>
  </div>
</section>
{% endblock %}
```

---

## ▶️ Sådan kører du lokalt

1. **Kør i Docker** (anbefalet førstegang):

```bash
docker compose up --build
```

Gå til `http://localhost:8000`.

2. **Kør uden Docker** (kræver Python 3.11):

```bash
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

---

## 🗺️ Næste trin (efter MVP)

* **Økonomi/XP**: belønning ved resolve, omkostning ved nye enheder/personale.
* **Personale/skills**: paramedic, firefighter, driver; skift og træthed.
* **Realtime UI**: HTMX partials til opdatering uden full reload.
* **Bykort**: simpelt grid/områder; responstid afhænger af afstand.
* **Svigt/risiko**: køretøj kan gå i stykker; hospitaler kan blive fulde.
* **Fraktioner/konkurrence**: (senere) coop eller leaderboards.

---

## 💡 Alternative stacks

* **Unity (C#) + Web API**: God hvis du senere vil have mobil/PC-klient.
* **Godot (GDScript/C#)**: Let engine med eksport til web/mobile.
* **Swift iOS-app**: Brug SwiftUI til en iPhone-klient; samme backend-API.

---

**Klar til at iterere**: Sig til hvilke features du vil have først (økonomi, personale, kort, AI-events), så udvider jeg koden stykvist.


