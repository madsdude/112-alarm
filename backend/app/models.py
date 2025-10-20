from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Station(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str
    grid_x: int = 0
    grid_y: int = 0


class Hospital(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str
    capacity: int = 10
    occupied: int = 0
    grid_x: int = 0
    grid_y: int = 0


class GameState(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    funds: int = 0
    xp: int = 0
    incidents_resolved: int = 0
    incidents_failed: int = 0


class Unit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str  # "fire" | "ambulance" | "police"
    name: str
    status: str = "available"  # available, enroute, at_scene, returning, broken, maintenance
    station_id: Optional[int] = Field(default=None, foreign_key="station.id")
    speed: float = 1.0
    condition: float = 1.0  # 0..1 – affects risk of breakdown
    location_x: int = 0
    location_y: int = 0
    home_x: int = 0
    home_y: int = 0
    down_until: Optional[datetime] = None


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
    grid_x: int = 0
    grid_y: int = 0
    xp_reward: int = 0
    cash_reward: int = 0
    response_started_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class Dispatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: int = Field(foreign_key="incident.id")
    unit_id: int = Field(foreign_key="unit.id")
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    arrive_at: Optional[datetime] = None
    return_at: Optional[datetime] = None
    travel_time_s: int = 0
    active: bool = True


class Personnel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    role: str  # paramedic | firefighter | driver
    skill: int = 1
    fatigue: float = 0.0  # 0-100 scale
    on_shift: bool = False
    rest_until: Optional[datetime] = None
    unit_id: Optional[int] = Field(default=None, foreign_key="unit.id")
