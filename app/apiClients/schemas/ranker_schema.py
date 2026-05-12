from pydantic import BaseModel


class RankingResponse(BaseModel):
    sorted: list[str]
    unknown: list[str]
