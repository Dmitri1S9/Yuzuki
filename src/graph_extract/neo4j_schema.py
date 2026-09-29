"""Uniqueness constraints, created once before writing."""
from yuzuki_local.external.neo4j_client import Neo4jClient

CONSTRAINTS = (
    "CREATE CONSTRAINT character_id IF NOT EXISTS FOR (n:Character) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT group_id IF NOT EXISTS FOR (n:Group) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT people_universe IF NOT EXISTS FOR (n:People) REQUIRE n.universe IS UNIQUE",
    "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (n:Concept) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT trait_name IF NOT EXISTS FOR (n:Trait) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT universe_name IF NOT EXISTS FOR (n:Universe) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT action_key IF NOT EXISTS FOR ()-[r:ACTION]-() REQUIRE r.edge_key IS UNIQUE",
    "CREATE CONSTRAINT described_as_key IF NOT EXISTS FOR ()-[r:DESCRIBED_AS]-() REQUIRE r.edge_key IS UNIQUE",
)


def ensure_constraints(client: Neo4jClient) -> list[str]:
    """Returns the statements that failed (e.g. a relationship-key constraint on a Neo4j edition that
    doesn't support one) -- MERGE by edge_key still de-duplicates without the DB-level guarantee, so a
    failure here is not fatal, just recorded for the report."""
    failed = []
    with client.session() as session:
        for stmt in CONSTRAINTS:
            try:
                session.run(stmt)
            except Exception as e:
                failed.append(f"{stmt} -> {e}")
    return failed
