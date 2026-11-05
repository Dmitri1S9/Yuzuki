from pydantic import BaseModel


class SymmetricRelation(BaseModel):
    members: list[str]          # 2 = pair, 3+ = clique


class DirectedRelation(BaseModel):
    source: str
    target: str


class SymmetricResponse(BaseModel):
    relations: list[SymmetricRelation] = []


class DirectedResponse(BaseModel):
    relations: list[DirectedRelation] = []