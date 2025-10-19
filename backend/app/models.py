from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


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
