from pydantic import BaseModel
from typing import Optional, Literal


class CharacterProfile(BaseModel):
    body_age: Optional[Literal["child", "adult", "elder"]] = None
    soul_age: Optional[Literal["child", "adult", "elder"]] = None
    gender: Literal["male", "female", "unknown"]
    species: str = "human"


class ProfileResponse(BaseModel):
    characters: dict[str, CharacterProfile]