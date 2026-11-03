class CharacterException(Exception):
    def __init__(self, universe_id: int | None = None, name: str | None = None):
        self.universe_id = universe_id
        self.name = name
        detail = f" ({name!r} in universe {universe_id})" if name is not None else ""
        self.message = f"💢💢💢💢💢 Character Exception, because the character is not found{detail}"
    def __str__(self):
        return repr(self.message)

class OpenAIException(Exception):
    def __init__(self):
        self.message = "💢💢💢💢💢 Problems on OpenAI side"
    def __str__(self):
        return repr(self.message)

class EmptyUniverseException(Exception):
    def __init__(self):
        self.message = "💢💢💢💢💢 No characters was found in this universe"
    def __str__(self):
        return repr(self.message)

class falseGroupTypeException(Exception):
    def __init__(self):
        self.message = "💢💢💢💢💢 Group type is not defined"
    def __str__(self):
        return repr(self.message)

class falseRelationTypeException(Exception):
    def __init__(self):
        self.message = "💢💢💢💢💢 Relation type is not defined"
    def __str__(self):
        return repr(self.message)
