"""Read-only universe browsing — thin wrappers over UniverseRepository."""
from fastapi import APIRouter, HTTPException

from src.api.schemas import UniverseOut
from src.repository import UniverseRepository

router = APIRouter(tags=["universes"])
_universe_repo = UniverseRepository()


@router.get("/universes", response_model=list[UniverseOut])
def list_universes():
    universes = _universe_repo.list_universes()
    return [UniverseOut(id=u.get_id(), name=u.get_name(), arc=u.get_arc()) for u in universes]


@router.get("/universes/{universe_id}", response_model=UniverseOut)
def get_universe(universe_id: int):
    u = _universe_repo.get_universe_by_id(universe_id)
    if u is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    return UniverseOut(id=u.get_id(), name=u.get_name(), arc=u.get_arc())
