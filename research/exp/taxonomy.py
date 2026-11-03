"""Закрытые словари: типы отношений, affinity, полюса черт. Все — из устоявшихся источников, не самодельные.

Отношения: Massey et al. 2015 (social / professional / familial + affinity pos/neg/neutral, разметка по
SparkNotes-пересказам — ближайший к вики жанр), свёрнутые до одного слова на тип; верхний уровень — 5 классов
Conan (Zhao et al. 2024): Romantic / Family / Ally / Adversarial / Business. Измерения Wish et al. 1976
(cooperative–hostile, equal–unequal, intense–superficial) выводятся из пары (type, affinity) и не спрашиваются.
"Classmate"/"member" нет намеренно: членство — факт группы (ребро MEMBER_OF), а не отношение двух людей.

Черты: полюса Big Five (Goldberg 1992; маркеры Saucier 1994 Mini-Markers) + Honesty-Humility из HEXACO
(Ashton & Lee 2007). Dark Triad не отдельная ось: в HEXACO его ядро ≈ низкий H (Lee & Ashton 2005).
"""

# type -> (definition shown to the model, Conan top-level class, NLI template; {a}=owner, {b}=other)
REL_TYPES: dict[str, tuple[str, str, str]] = {
    "family":       ("relatives by blood or marriage: parent, child, sibling, grandparent, cousin, in-law",
                     "Family",      "{a} and {b} are relatives."),
    "romance":      ("lovers, spouses, dating, or one has a crush / unrequited love for the other",
                     "Romantic",    "{a} and {b} are romantically involved or one loves the other."),
    "friend":       ("the text calls them friends or shows a close personal bond",
                     "Ally",        "{a} and {b} are friends."),
    "acquaintance": ("they know each other and get along or not, but no close bond is stated",
                     "Ally",        "{a} and {b} know each other but are not close."),
    "teammate":     ("they act together toward a shared goal: same team in a fight, exam, mission or project",
                     "Ally",        "{a} and {b} work together as a team."),
    "mentor":       ("the page owner teaches, trains or guides the other person",
                     "Business",    "{a} teaches or guides {b}."),
    "student":      ("the other person teaches, trains or guides the page owner",
                     "Business",    "{b} teaches or guides {a}."),
    "superior":     ("the page owner has formal authority over the other: boss, leader, master, commander",
                     "Business",    "{a} has authority over {b}."),
    "subordinate":  ("the other has formal authority over the page owner",
                     "Business",    "{b} has authority over {a}."),
    "rival":        ("they compete for the same goal without wishing each other harm",
                     "Adversarial", "{a} and {b} are rivals."),
    "enemy":        ("they fight, attack, or try to harm or defeat each other",
                     "Adversarial", "{a} and {b} are enemies."),
}
UNSPECIFIED = "unspecified"  # связь есть, тип в абзаце не назван (план владельца: "просто связь есть")
REL_TYPE_ENUM = [*REL_TYPES, UNSPECIFIED]

AFFINITY = ["positive", "neutral", "negative"]  # Massey et al. 2015

# pole -> (short definition, HEXACO/Big Five factor)
TRAIT_POLES: dict[str, str] = {
    "E+": "extraverted: sociable, talkative, energetic, bold",
    "E-": "introverted: quiet, shy, reserved, withdrawn",
    "A+": "agreeable: kind, warm, sympathetic, cooperative, forgiving",
    "A-": "disagreeable: harsh, rude, cold, aggressive, mocking",
    "C+": "conscientious: organized, efficient, careful, disciplined, practical",
    "C-": "unconscientious: careless, impulsive, lazy, disorganized, reckless",
    "N+": "emotionally unstable: anxious, fearful, moody, insecure, easily upset",
    "N-": "emotionally stable: calm, brave, composed, hard to upset",
    "O+": "open: intelligent, creative, curious, imaginative",
    "O-": "closed: conventional, unimaginative, oblivious, simple",
    "H+": "honest-humble: sincere, modest, fair, unassuming",
    "H-": "dishonest-proud: deceitful, arrogant, greedy, hypocritical, lewd, boastful",
}
TRAIT_STATUS = ["actual", "apparent", "negated", "other_character"]
