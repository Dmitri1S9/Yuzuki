from pydantic import BaseModel


class GroupPairsResponse(BaseModel):
    pairs: list[list[str]] = []
