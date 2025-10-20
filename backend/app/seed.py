from sqlmodel import delete

from .models import (
    Station,
    Hospital,
    Unit,
    GameState,
    Personnel,
    Incident,
    Dispatch,
)
from .repo import get_session


def seed():
    with get_session() as s:
        # Clean the slate so seed can be rerun safely
        for model in [Dispatch, Incident, Personnel, Unit, Hospital, Station, GameState]:
            s.exec(delete(model))
        s.commit()

        stations = [
            Station(name="Station Randers", city="Randers", grid_x=3, grid_y=4),
            Station(name="Station Aarhus", city="Aarhus", grid_x=7, grid_y=6),
        ]

        hospitals = [
            Hospital(name="Randers Hospital", city="Randers", capacity=20, grid_x=2, grid_y=5),
            Hospital(name="Aarhus Hospital", city="Aarhus", capacity=40, grid_x=8, grid_y=5),
        ]

        units = [
            Unit(
                kind="fire",
                name="BR-1",
                station_id=1,
                speed=1.2,
                home_x=stations[0].grid_x,
                home_y=stations[0].grid_y,
                location_x=stations[0].grid_x,
                location_y=stations[0].grid_y,
            ),
            Unit(
                kind="fire",
                name="BR-2",
                station_id=1,
                speed=1.0,
                home_x=stations[0].grid_x,
                home_y=stations[0].grid_y,
                location_x=stations[0].grid_x,
                location_y=stations[0].grid_y,
            ),
            Unit(
                kind="ambulance",
                name="AMB-1",
                station_id=1,
                speed=1.5,
                home_x=stations[0].grid_x,
                home_y=stations[0].grid_y,
                location_x=stations[0].grid_x,
                location_y=stations[0].grid_y,
            ),
            Unit(
                kind="ambulance",
                name="AMB-2",
                station_id=2,
                speed=1.4,
                home_x=stations[1].grid_x,
                home_y=stations[1].grid_y,
                location_x=stations[1].grid_x,
                location_y=stations[1].grid_y,
            ),
            Unit(
                kind="police",
                name="POL-1",
                station_id=2,
                speed=1.6,
                home_x=stations[1].grid_x,
                home_y=stations[1].grid_y,
                location_x=stations[1].grid_x,
                location_y=stations[1].grid_y,
            ),
        ]

        personnel = [
            Personnel(name="Eva", role="driver", skill=2, unit_id=1, on_shift=True),
            Personnel(name="Nikolaj", role="firefighter", skill=3, unit_id=1, on_shift=True),
            Personnel(name="Sara", role="firefighter", skill=2, unit_id=2, on_shift=True),
            Personnel(name="Mikkel", role="driver", skill=2, unit_id=2, on_shift=True),
            Personnel(name="Ida", role="paramedic", skill=3, unit_id=3, on_shift=True),
            Personnel(name="Jonas", role="driver", skill=2, unit_id=3, on_shift=True),
            Personnel(name="Lene", role="paramedic", skill=3, unit_id=4, on_shift=True),
            Personnel(name="Thomas", role="driver", skill=2, unit_id=4, on_shift=True),
        ]

        gamestate = GameState(funds=2000, xp=0)

        for entry in stations + hospitals + units + personnel + [gamestate]:
            s.add(entry)
        s.commit()
