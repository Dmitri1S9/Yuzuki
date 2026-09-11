"""Relation (character-to-character, directed or symmetric) and GroupRelation
(allied/rival between two groups). Both read-only after construction."""


class Relation:
    def __init__(self, relation_type: str, count: int, source_level: str,
                 members: list[str] | None = None,
                 source: str | None = None, target: str | None = None):
        self._relation_type = relation_type
        self._count = count
        self._source_level = source_level
        self._members = list(members) if members is not None else None
        self._source = source
        self._target = target

    def get_type(self) -> str:
        return self._relation_type

    def get_count(self) -> int:
        return self._count

    def get_source_level(self) -> str:
        return self._source_level

    def is_directed(self) -> bool:
        return self._members is None

    def get_members(self) -> list[str] | None:
        return list(self._members) if self._members is not None else None

    def get_source(self) -> str | None:
        return self._source

    def get_target(self) -> str | None:
        return self._target

    def _identity(self) -> tuple:
        endpoints = (self._source, self._target) if self.is_directed() else tuple(sorted(self._members))
        return (self._relation_type, self._source_level, endpoints)

    @classmethod
    def help(cls) -> list[str]:
        fields = ["type", "count", "source_level", "members", "source", "target", "is_directed"]
        print(f"{cls.__name__} — fields: {', '.join(fields)} (each via get_<field>() / is_directed())")
        return fields

    def __repr__(self) -> str:
        if self.is_directed():
            return f"Relation({self._relation_type!r}, {self._source!r} -> {self._target!r})"
        return f"Relation({self._relation_type!r}, {self._members!r})"

    def __str__(self) -> str:
        return self._relation_type

    def __eq__(self, other) -> bool:
        if not isinstance(other, Relation):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())


class GroupRelation:
    def __init__(self, group_a: str, group_b: str, kind: str):
        self._group_a = group_a
        self._group_b = group_b
        self._kind = kind

    def get_group_a(self) -> str:
        return self._group_a

    def get_group_b(self) -> str:
        return self._group_b

    def get_kind(self) -> str:
        return self._kind

    @classmethod
    def help(cls) -> list[str]:
        fields = ["group_a", "group_b", "kind"]
        print(f"{cls.__name__} — fields: {', '.join(fields)} (each via get_<field>())")
        return fields

    def __repr__(self) -> str:
        return f"GroupRelation({self._group_a!r}, {self._group_b!r}, kind={self._kind!r})"

    def __str__(self) -> str:
        return f"{self._group_a} {self._kind} {self._group_b}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, GroupRelation):
            return NotImplemented
        return (self._kind, tuple(sorted((self._group_a, self._group_b)))) == \
               (other._kind, tuple(sorted((other._group_a, other._group_b))))

    def __hash__(self) -> int:
        return hash((self._kind, tuple(sorted((self._group_a, self._group_b)))))
