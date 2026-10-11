from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MapMarker, Team
from ..security import current_team, limiter
from ..service import current_puzzle, next_step, progress_for, require_event, split_markers, team_puzzles

router = APIRouter(prefix="/api", tags=["map"])


def marker_out(marker: MapMarker) -> dict:
    # No database id: gaps in a sequence would hint at how many markers are still hidden.
    return {
        "name": marker.name, "description": marker.description, "directions": marker.directions,
        "kind": marker.kind, "x": marker.x, "y": marker.y, "lat": marker.lat, "lng": marker.lng,
    }


@router.get("/map")
def team_map(team: Team = Depends(current_team), db: Session = Depends(get_db)):
    """The map as this team may see it right now. Locked markers are filtered here, on the server,
    so their names and coordinates never reach a browser."""
    limiter.check(f"map:{team.id}", 60)
    event = require_event(db)
    visible, _hidden = split_markers(db, event, team)
    puzzles = team_puzzles(db, event, team.id)
    puzzle = current_puzzle(puzzles, progress_for(db, team.id))
    position = puzzles.index(puzzle) + 1 if puzzle else 0
    return {
        "provider": event.map_provider,
        "image_url": event.map_image_url if event.map_provider == "image" else "",
        "center": {"lat": event.map_lat, "lng": event.map_lng, "zoom": event.map_zoom},
        "markers": [marker_out(m) for m in visible],
        "next_step": next_step(event, team, puzzle, position, visible),
    }
