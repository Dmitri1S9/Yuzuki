"""Universe — one universe/arc: its roster of Characters and its Groups.
Read-only after construction."""
from src.domain.character import Character
from src.domain.group import Group


class Universe:
    def __init__(self, universe_id: int, name: str, arc: str | None,
                 roster: list[Character] | None = None, groups: list[Group] | None = None,
                 anilist_title: str | None = None):
        self._id = universe_id
        self._name = name
        self._arc = arc
        self._roster = list(roster or [])
        self._groups = list(groups or [])
        self._anilist_title = anilist_title

    def get_id(self) -> int:
        return self._id

    def get_name(self) -> str:
        return self._name

    def get_arc(self) -> str | None:
        return self._arc

    def get_anilist_title(self) -> str:
        """The AniList media title to search for this universe — its own
        override if a stage-1 run was given one (an arc's title can be
        unrelated-looking to the franchise's main name), else its display
        name."""
        return self._anilist_title or self._name

    def get_roster(self) -> list[Character]:
        return list(self._roster)

    def get_groups(self) -> list[Group]:
        return list(self._groups)

    def get_character(self, name: str) -> Character | None:
        for c in self._roster:
            if c.get_name() == name:
                return c
        return None

    @classmethod
    def help(cls) -> list[str]:
        fields = ["id", "name", "arc", "roster", "groups"]
        print(f"{cls.__name__} — fields: {', '.join(fields)} (each via get_<field>()); "
              "get_character(name) looks one up by name")
        return fields

    def __repr__(self) -> str:
        return f"Universe({self._name!r}, arc={self._arc!r})"

    def __str__(self) -> str:
        return f"{self._name} ({self._arc})" if self._arc else self._name

    def __eq__(self, other) -> bool:
        if not isinstance(other, Universe):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)
