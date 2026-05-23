from app.apiClients.clientX import XClient
from app.tasks import rank_task, flag_task, profile_task
from db.service import create_universe

UNIVERSE_NAME = "Classroom of the Elite"



class UniverseBuilder:

    def __init__(self, universe: str, characters: list[str], arc: str | None = None) -> None:
        self.universe = universe
        self.characters = characters
        self.arc = arc
        self.universe_id: int | None = None

    def _flag(self, flag_name: str):
        return flag_task.delay(flag_name, self.characters, self.universe, self.universe_id, arc=self.arc)

    def _rank(self, prompt: str, parameter: str):
        return rank_task.delay(prompt, self.characters, self.universe, self.universe_id, parameter, arc=self.arc)

    def _profile(self):
        return profile_task.delay(self.characters, self.universe, self.universe_id, arc=self.arc)

    def collect_universe(self) -> None:
        self.universe_id = create_universe(self.universe, self.characters, self.arc)

        # --- profile (1 task) ---
        self._profile()

        # --- rankers (6 tasks) ---
        self._rank("user_prompt_combat_potential", "combat_potential")
        self._rank("user_prompt_intellect_potential", "intellect")
        self._rank("user_prompt_authority_scope", "authority_scope")
        self._rank("user_prompt_loyalty_command", "loyalty_command")
        self._rank("user_prompt_social_impact", "social_impact")
        self._rank("user_prompt_wealth", "wealth")

        # --- flags (1 per task) ---
        all_flags = [
            # personality
            "manipulative", "honest", "impulsive", "secretive",
            "self_sacrificing", "adaptable", "loyal", "empathetic",
            "cruel", "arrogant", "competitive", "ruthless",
            "is_strategist", "has_humor",
            # appearance
            "is_physically_attractive", "is_intimidating",
            "is_muscular", "has_distinctive_feature", "is_well_groomed",
            # motivation
            "goal_power", "goal_love", "goal_knowledge",
            "goal_revenge", "goal_survival", "goal_duty",
            "goal_freedom", "goal_recognition", "goal_protection",
            # domain
            "military", "politics", "science",
            "art", "education", "crime", "commerce",
            # state
            "has_magic", "has_tragic_past", "is_strong_willed",
            "is_provocative", "is_loner", "is_unstable", "is_fanatical",
            # worldview
            "is_idealist", "is_nihilist", "is_pragmatist",
            "is_hedonist", "is_machiavellian",
            "is_revolutionary", "is_fatalist",
            # weakness
            "has_physical_weakness", "has_psychological_weakness",
        ]
        for f in all_flags:
            self._flag(f)


if __name__ == "__main__":
    import json

    with open("app/data/characters_cote.json", "r") as f:
        COTE_CHARACTERS = json.load(f)
        ch1 = COTE_CHARACTERS["Start of Year 1 (Y1V1)"] 
        ch2 = COTE_CHARACTERS["Start of Year 2 (Y2V1)"] 
        ch3 = COTE_CHARACTERS["Start of Year 3 (Y3V1)"] 
    

    builder = UniverseBuilder(UNIVERSE_NAME, ch1, arc="Year 1")
    builder.collect_universe()