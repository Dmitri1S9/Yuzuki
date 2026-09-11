from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG = parse_universe_args("Classroom of the Elite", "Year 1")

# curve shape per relation type — distinct roundness/direction so 2+ edges
# between the same pair (different types) render as separate visible
# curves instead of stacking on top of each other and hiding one another.
RELATION_STYLE = {
    "for":     {"color": "#2ecc71", "directed": True,  "smooth": {"type": "curvedCW",  "roundness": 0.15}},
    "want":    {"color": "#e84393", "directed": True,  "smooth": {"type": "curvedCW",  "roundness": 0.35}},
    "against": {"color": "#e74c3c", "directed": False, "smooth": {"type": "curvedCCW", "roundness": 0.15}},
    "with":    {"color": "#3498db", "directed": False, "smooth": {"type": "curvedCCW", "roundness": 0.35}},
}

GROUP_RELATION_STYLE = {
    "allied": {"color": "#2ecc71"},
    "rival":  {"color": "#e74c3c"},
}

NODE_PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
                "#e67e22", "#c0392b", "#16a085", "#8e44ad", "#2980b9", "#d35400"]

AREA_PALETTE = ["#8e44ad", "#16a085", "#c0392b", "#2980b9", "#d35400", "#27ae60"]
