import random
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlmodel import select

from .models import GameState, Hospital, Station, Unit, Incident, Dispatch, Personnel
from .repo import get_session

CITIES_FALLBACK = ["Randers", "Aarhus", "Viborg", "Silkeborg", "Aalborg"]

INCIDENT_TYPES = [
    ("fire", {"fire": (1, 3), "ambulance": (0, 1)}),
    ("medical", {"fire": (0, 1), "ambulance": (1, 2)}),
    ("traffic", {"fire": (0, 1), "ambulance": (1, 2)}),
]

BASE_GRID_SIZE = 12
MIN_TRAVEL_TIME = 45
RESOLVE_TICK_BASE = 90
RETURN_BUFFER = 20


def random_city(session):
    cities = [s.city for s in session.exec(select(Station)).all()] or CITIES_FALLBACK
    return random.choice(cities)


def grid_bounds(value: int) -> int:
    return max(0, min(BASE_GRID_SIZE, value))


def city_anchor(session, city: str):
    station = session.exec(select(Station).where(Station.city == city)).first()
    if station:
        return station.grid_x, station.grid_y
    hospital = session.exec(select(Hospital).where(Hospital.city == city)).first()
    if hospital:
        return hospital.grid_x, hospital.grid_y
    return random.randint(0, BASE_GRID_SIZE), random.randint(0, BASE_GRID_SIZE)


def ensure_gamestate(session) -> GameState:
    gs = session.get(GameState, 1)
    if not gs:
        gs = GameState(id=1, funds=0, xp=0)
        session.add(gs)
        session.commit()
        session.refresh(gs)
    return gs


def unit_personnel(session, unit_id: int) -> List[Personnel]:
    return session.exec(select(Personnel).where(Personnel.unit_id == unit_id)).all()


def fatigue_tick(personnel: Iterable[Personnel], delta: float):
    for member in personnel:
        member.fatigue = max(0.0, min(100.0, member.fatigue + delta))
        if member.fatigue >= 95 and not member.rest_until:
            member.rest_until = datetime.utcnow() + timedelta(hours=2)
            member.on_shift = False


def spawn_incident():
    with get_session() as s:
        typ, req = random.choice(INCIDENT_TYPES)
        city = random_city(s)
        anchor_x, anchor_y = city_anchor(s, city)
        x = grid_bounds(anchor_x + random.randint(-3, 3))
        y = grid_bounds(anchor_y + random.randint(-3, 3))
        severity = random.randint(1, 5)
        inc = Incident(
            type=typ,
            severity=severity,
            city=city,
            need_fire=random.randint(*req["fire"]),
            need_ambulance=random.randint(*req["ambulance"]),
            deadline_s=random.choice([240, 300, 360]),
            grid_x=x,
            grid_y=y,
            xp_reward=severity * 8 + random.randint(0, 6),
            cash_reward=severity * 150 + random.randint(0, 100),
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
        if inc.status in {"resolved", "failed"}:
            return False
        if unit.status != "available" or (unit.down_until and unit.down_until > datetime.utcnow()):
            return False

        crew = unit_personnel(s, unit.id)
        if not crew:
            return False

        required_roles = {"driver"}
        if unit.kind == "fire":
            required_roles.add("firefighter")
        if unit.kind == "ambulance":
            required_roles.add("paramedic")

        available_roles = {member.role for member in crew if member.fatigue < 98 and not member.rest_until}
        if not required_roles.issubset(available_roles):
            return False

        now = datetime.utcnow()
        distance = abs(unit.location_x - inc.grid_x) + abs(unit.location_y - inc.grid_y)
        travel_time = int(max(MIN_TRAVEL_TIME, (distance / max(unit.speed, 0.5)) * 40))
        arrive_at = now + timedelta(seconds=travel_time)

        unit.status = "enroute"
        unit.down_until = None
        unit.condition = max(0.1, unit.condition - random.uniform(0.02, 0.08))

        for member in crew:
            member.on_shift = True
            member.rest_until = None
            member.fatigue = min(100.0, member.fatigue + random.uniform(2, 5))
            s.add(member)

        dispatch = Dispatch(
            incident_id=inc.id,
            unit_id=unit.id,
            arrive_at=arrive_at,
            travel_time_s=travel_time,
        )

        s.add(dispatch)
        if inc.status == "new":
            inc.status = "responding"
            inc.response_started_at = now
        s.add(unit)
        s.add(inc)
        s.commit()
        return True


def _resolve_requirements(session, inc: Incident) -> Dict[str, int]:
    dispatched = session.exec(select(Dispatch).where(Dispatch.incident_id == inc.id, Dispatch.active)).all()
    counts = {"fire": 0, "ambulance": 0, "other": 0}
    for di in dispatched:
        unit = session.get(Unit, di.unit_id)
        if not unit:
            continue
        if unit.status not in {"enroute", "at_scene"}:
            continue
        if unit.kind == "fire":
            counts["fire"] += 1
        elif unit.kind == "ambulance":
            counts["ambulance"] += 1
        else:
            counts["other"] += 1
    return counts


def _nearest_hospital(session, inc: Incident) -> Optional[Hospital]:
    hospitals = session.exec(select(Hospital)).all()
    if not hospitals:
        return None
    hospitals.sort(key=lambda h: abs(h.grid_x - inc.grid_x) + abs(h.grid_y - inc.grid_y))
    return hospitals[0]


def tick():
    now = datetime.utcnow()
    with get_session() as s:
        ensure_gamestate(s)
        for unit in s.exec(select(Unit)):
            if unit.status == "broken" and unit.down_until and unit.down_until <= now:
                unit.status = "maintenance"
                unit.down_until = now + timedelta(minutes=10)
                s.add(unit)
            elif unit.status == "maintenance" and unit.down_until and unit.down_until <= now:
                unit.status = "available"
                unit.condition = min(1.0, unit.condition + 0.25)
                unit.location_x = unit.home_x
                unit.location_y = unit.home_y
                unit.down_until = None
                s.add(unit)

        for dispatch in s.exec(select(Dispatch).where(Dispatch.active)):
            unit = s.get(Unit, dispatch.unit_id)
            inc = s.get(Incident, dispatch.incident_id)
            if not unit or not inc:
                dispatch.active = False
                s.add(dispatch)
                continue

            if unit.status == "enroute" and dispatch.arrive_at and now >= dispatch.arrive_at:
                if random.random() < 0.05 * (1.2 - unit.condition):
                    unit.status = "broken"
                    unit.down_until = now + timedelta(minutes=15)
                    dispatch.active = False
                else:
                    unit.status = "at_scene"
                    unit.location_x = inc.grid_x
                    unit.location_y = inc.grid_y
                    dispatch.arrive_at = now
                    dispatch.return_at = now + timedelta(seconds=RESOLVE_TICK_BASE + inc.severity * 30)
                    if inc.status == "responding":
                        counts = _resolve_requirements(s, inc)
                        if counts["fire"] >= inc.need_fire and counts["ambulance"] >= inc.need_ambulance:
                            inc.status = "resolving"
                            inc.response_started_at = now
                s.add(unit)
                s.add(dispatch)
                s.add(inc)
                continue

            if unit.status == "at_scene" and dispatch.return_at and now >= dispatch.return_at:
                unit.status = "returning"
                dispatch.return_at = now + timedelta(seconds=max(MIN_TRAVEL_TIME, dispatch.travel_time_s) + RETURN_BUFFER)
                s.add(unit)
                s.add(dispatch)
                continue

            if unit.status == "returning" and dispatch.return_at and now >= dispatch.return_at:
                unit.status = "available"
                unit.location_x = unit.home_x
                unit.location_y = unit.home_y
                dispatch.active = False
                s.add(unit)
                s.add(dispatch)

        for inc in s.exec(select(Incident).where(Incident.status.in_(["new", "responding", "resolving"]))):
            if inc.status in {"new", "responding"}:
                counts = _resolve_requirements(s, inc)
                if counts["fire"] >= inc.need_fire and counts["ambulance"] >= inc.need_ambulance:
                    inc.status = "resolving"
                    inc.response_started_at = inc.response_started_at or now
            if inc.status == "resolving":
                resolve_time = RESOLVE_TICK_BASE + inc.severity * 40
                if inc.response_started_at and (now - inc.response_started_at).total_seconds() >= resolve_time:
                    hospital = _nearest_hospital(s, inc)
                    ambulances_needed = inc.need_ambulance
                    if hospital and hospital.occupied + ambulances_needed <= hospital.capacity:
                        hospital.occupied += max(1, ambulances_needed)
                        inc.status = "resolved"
                        inc.resolved_at = now
                        gs = ensure_gamestate(s)
                        gs.funds += inc.cash_reward
                        gs.xp += inc.xp_reward
                        gs.incidents_resolved += 1
                        s.add(hospital)
                        s.add(gs)
                    else:
                        inc.status = "failed"
                        inc.resolved_at = now
                        gs = ensure_gamestate(s)
                        gs.incidents_failed += 1
                        gs.funds = max(0, gs.funds - int(inc.cash_reward * 0.2))
                        s.add(gs)
            if inc.status in {"new", "responding"}:
                age = (now - inc.created_at).total_seconds()
                if age > inc.deadline_s:
                    inc.status = "failed"
                    gs = ensure_gamestate(s)
                    gs.incidents_failed += 1
                    s.add(gs)
            s.add(inc)

        for member in s.exec(select(Personnel)):
            if member.rest_until and member.rest_until <= now:
                member.rest_until = None
                member.fatigue = max(10.0, member.fatigue - 20)
            unit = member.unit_id and s.get(Unit, member.unit_id)
            if unit and unit.status in {"enroute", "at_scene", "returning"}:
                fatigue_tick([member], random.uniform(3, 6))
            else:
                fatigue_tick([member], -random.uniform(1, 3))
                if member.fatigue < 70:
                    member.on_shift = True
            s.add(member)

        s.commit()
