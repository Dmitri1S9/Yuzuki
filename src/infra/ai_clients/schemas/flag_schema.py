from pydantic import BaseModel


class FlagRankResponse(BaseModel):
    # unknown declared first: the prompt asks the model to commit to who it
    # doesn't recognize before ranking anyone (see system_prompt_flag_rank.j2
    # rule 8) — field order shapes generation order for structured output,
    # same reason RankingResponse's own field order matters.
    unknown: list[str] = []
    sorted: list[str]
