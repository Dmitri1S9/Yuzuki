from pydantic import BaseModel
from typing import Optional, Literal


class Group(BaseModel):
    name: str
    group_type: Literal["small", "medium", "large"]
    members: list[str]
    leader: Optional[str] = None


class GroupsResponse(BaseModel):
    groups: list[Group] = []
    isolates: list[str] = []
