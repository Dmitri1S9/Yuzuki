"""Serves character portrait bytes straight from Postgres — replaces the old
StaticFiles mount over media/characters/*.jpg (see api/main.py)."""
import hashlib

from fastapi import APIRouter, HTTPException, Request, Response

from src.repository import CharacterRepository

router = APIRouter(tags=["media"])
_character_repo = CharacterRepository()


@router.get("/characters/{universe_id}/{name}/portrait")
def get_character_portrait(universe_id: int, name: str, request: Request):
    portrait = _character_repo.get_character_portrait(universe_id, name)
    if portrait is None:
        raise HTTPException(status_code=404, detail=f"no portrait for {name!r} in universe {universe_id}")
    image_bytes, content_type = portrait

    # ETag by content hash: correctly invalidates exactly when the bytes
    # change, replacing the old filename's "?v=<timestamp>" cache-buster.
    etag = hashlib.sha1(image_bytes).hexdigest()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(content=image_bytes, media_type=content_type,
                     headers={"ETag": etag, "Cache-Control": "public, max-age=31536000"})
