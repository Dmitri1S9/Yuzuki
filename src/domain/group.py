"""Group — one medium/large character group. Read-only after construction."""


class Group:
    def __init__(self, name: str, group_type: str, members: list[str],
                 name_variants: list[str] | None = None, passes: list[int] | None = None):
        self._name = name
        self._group_type = group_type
        self._members = list(members)
        self._name_variants = list(name_variants or [])
        self._passes = list(passes or [])

    def get_name(self) -> str:
        return self._name

    def get_type(self) -> str:
        return self._group_type

    def get_members(self) -> list[str]:
        return list(self._members)

    def get_name_variants(self) -> list[str]:
        return list(self._name_variants)

    def get_passes(self) -> list[int]:
        return list(self._passes)

    @classmethod
    def help(cls) -> list[str]:
        fields = ["name", "type", "members", "name_variants", "passes"]
        print(f"{cls.__name__} — fields: {', '.join(fields)} (each via get_<field>())")
        return fields

    def __repr__(self) -> str:
        return f"Group({self._name!r}, type={self._group_type!r})"

    def __str__(self) -> str:
        return self._name

    def __eq__(self, other) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return (self._group_type, self._name) == (other._group_type, other._name)

    def __hash__(self) -> int:
        return hash((self._group_type, self._name))
