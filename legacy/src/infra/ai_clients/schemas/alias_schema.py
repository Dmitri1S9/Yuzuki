from pydantic import BaseModel
from typing import Optional


class NameEntry(BaseModel):
    name: str
    other_name: Optional[str] = None


class AliasNamesResponse(BaseModel):
    entries: list[NameEntry] = []
