"""Character — one roster member. Built once from repository rows and
read-only afterward: private state, getters only, no setters.

get_<param>() (get_combat_potential(), get_cruel(), get_gender(), ...) are
not hand-written — the loop at the bottom of this file generates one getter
per name in parameters.PROFILE_PARAMS / ORDINAL_PARAMS / FLAG_PARAMS, the
single source of truth (parameters.json). Add a parameter there and its
getter appears here automatically. Call Character.help() for the full list.
"""
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS, PROFILE_PARAMS


class Character:
    def __init__(self, name: str, universe_id: int, aliases: list[str] | None = None,
                 low_info: bool = False, profile: dict | None = None,
                 ordinals: dict | None = None, flags: dict | None = None):
        self._name = name
        self._universe_id = universe_id
        self._aliases = list(aliases or [])
        self._low_info = low_info
        self._profile = dict(profile or {})
        self._ordinals = dict(ordinals or {})
        self._flags = dict(flags or {})

    def get_name(self) -> str:
        return self._name

    def get_universe_id(self) -> int:
        return self._universe_id

    def get_aliases(self) -> list[str]:
        return list(self._aliases)

    def is_low_info(self) -> bool:
        return self._low_info

    def get_profile_field(self, name: str):
        if name not in PROFILE_PARAMS:
            raise ValueError(f"unknown profile field: {name!r}")
        return self._profile.get(name)

    def get_ordinal(self, name: str):
        if name not in ORDINAL_PARAMS:
            raise ValueError(f"unknown ordinal parameter: {name!r}")
        return self._ordinals.get(name)

    def get_flag(self, name: str):
        if name not in FLAG_PARAMS:
            raise ValueError(f"unknown flag parameter: {name!r}")
        return self._flags.get(name)

    @classmethod
    def help(cls) -> list[str]:
        """List every parameter available via get_<name>() / obj['<name>'],
        sourced live from parameters.json — never goes stale by hand."""
        names = list(PROFILE_PARAMS) + list(ORDINAL_PARAMS) + list(FLAG_PARAMS)
        print(f"{cls.__name__} — identity: name, universe_id, aliases, low_info")
        print(f"{cls.__name__} — {len(PROFILE_PARAMS)} profile field(s): {', '.join(PROFILE_PARAMS)}")
        print(f"{cls.__name__} — {len(ORDINAL_PARAMS)} ordinal(s): {', '.join(ORDINAL_PARAMS)}")
        print(f"{cls.__name__} — {len(FLAG_PARAMS)} flag(s): {', '.join(FLAG_PARAMS)}")
        print("each reachable as get_<name>() or character['<name>']")
        return names

    def __repr__(self) -> str:
        return f"Character({self._name!r})"

    def __str__(self) -> str:
        return self._name

    def __eq__(self, other) -> bool:
        if not isinstance(other, Character):
            return NotImplemented
        return (self._universe_id, self._name) == (other._universe_id, other._name)

    def __hash__(self) -> int:
        return hash((self._universe_id, self._name))

    def __getitem__(self, name: str):
        if name in PROFILE_PARAMS:
            return self.get_profile_field(name)
        if name in ORDINAL_PARAMS:
            return self.get_ordinal(name)
        if name in FLAG_PARAMS:
            return self.get_flag(name)
        raise KeyError(name)


def _make_profile_getter(field_name: str):
    def getter(self: Character):
        return self._profile.get(field_name)
    return getter


def _make_ordinal_getter(param_name: str):
    def getter(self: Character):
        return self._ordinals.get(param_name)
    return getter


def _make_flag_getter(param_name: str):
    def getter(self: Character):
        return self._flags.get(param_name)
    return getter


for _name in PROFILE_PARAMS:
    setattr(Character, f"get_{_name}", _make_profile_getter(_name))
for _name in ORDINAL_PARAMS:
    setattr(Character, f"get_{_name}", _make_ordinal_getter(_name))
for _name in FLAG_PARAMS:
    setattr(Character, f"get_{_name}", _make_flag_getter(_name))
del _name
