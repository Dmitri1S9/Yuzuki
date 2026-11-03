"""Uniqueness constraints, created once before writing."""
from .external.neo4j_client import Neo4jClient

CONSTRAINTS = (
    # Character/Group are keyed on `name` alone, not a "Universe::Name" composite id -- the universe tie is
    # the (:Character)-[:IN_UNIVERSE]->(:Universe) edge written alongside every such node, never a string.
    "CREATE CONSTRAINT v3_character_name IF NOT EXISTS FOR (n:Character) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT v3_group_name IF NOT EXISTS FOR (n:Group) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT v3_people_universe IF NOT EXISTS FOR (n:People) REQUIRE n.universe IS UNIQUE",
    "CREATE CONSTRAINT v3_concept_name IF NOT EXISTS FOR (n:Concept) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT v3_universe_name IF NOT EXISTS FOR (n:Universe) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT v3_edge_key IF NOT EXISTS FOR ()-[r:EDGE]-() REQUIRE r.edge_key IS UNIQUE",
    "CREATE CONSTRAINT v3_has_property_key IF NOT EXISTS FOR ()-[r:HAS_PROPERTY]-() REQUIRE r.edge_key IS UNIQUE",
)


def ensure_constraints(client: Neo4jClient) -> list[str]:
    failed = []
    with client.session() as session:
        for stmt in CONSTRAINTS:
            try:
                session.run(stmt)
            except Exception as e:
                failed.append(f"{stmt} -> {e}")
    return failed
