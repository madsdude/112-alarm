import random
from datetime import datetime
from sqlmodel import select

from .models import Station, Unit, Incident, Dispatch
from .repo import get_session

CITIES_FALLBACK = ["Randers", "Aarhus", "Viborg", "Silkeborg", "Aalborg"]

INCIDENT_TYPES = [
    ("fire", {"fire": (1, 3), "ambulance": (0, 1)}),
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
            deadline_s=random.choice([180, 240, 300]),
        )
        s.add(inc)
        s.commit()
        s.refresh(inc)
        return inc


def dispatch_unit(incident_id: int, unit_id: int) -> bool:
    with get_session() as s:
        inc = s.get(Incident, incident_id)
        unit = s.get(Unit, unit_id)
        if not inc or not unit:
            return False
        if unit.status != "available":
            return False
        unit.status = "enroute"
        s.add(Dispatch(incident_id=inc.id, unit_id=unit.id))
        if inc.status == "new":
            inc.status = "responding"
        s.add(unit)
        s.add(inc)
        s.commit()
        return True


def tick():
    now = datetime.utcnow()
    with get_session() as s:
        incidents = s.exec(
            select(Incident).where(Incident.status.in_(["new", "responding", "resolving"]))
        ).all()
        for inc in incidents:
            if inc.status in ("new", "responding"):
                dispatched = s.exec(select(Dispatch).where(Dispatch.incident_id == inc.id)).all()
                fire_count = 0
                amb_count = 0
                for di in dispatched:
                    u = s.get(Unit, di.unit_id)
                    if not u:
                        continue
                    if u.kind == "fire":
                        fire_count += 1
                    if u.kind == "ambulance":
                        amb_count += 1
                if fire_count >= inc.need_fire and amb_count >= inc.need_ambulance:
                    inc.status = "resolving"
            elif inc.status == "resolving":
                age = (now - inc.created_at).total_seconds()
                if age > 60 + 20 * inc.severity:
                    inc.status = "resolved"
                    for di in s.exec(select(Dispatch).where(Dispatch.incident_id == inc.id)):
                        u = s.get(Unit, di.unit_id)
                        if u:
                            u.status = "returning"
                            s.add(u)
        for u in s.exec(select(Unit).where(Unit.status == "returning")):
            u.status = "available"
            s.add(u)
        for inc in s.exec(select(Incident).where(Incident.status.in_(["new", "responding"]))):
            age = (now - inc.created_at).total_seconds()
            if age > inc.deadline_s:
                inc.status = "failed"
                s.add(inc)
        s.commit()
