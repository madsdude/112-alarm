from sqlmodel import select

from .models import Station, Hospital, Unit
from .repo import get_session


def seed():
    with get_session() as s:
        if s.exec(select(Station)).first():
            return
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
        for entry in stations + hospitals + units:
            s.add(entry)
        s.commit()
