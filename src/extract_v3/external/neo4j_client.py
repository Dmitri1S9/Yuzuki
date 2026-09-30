"""Neo4j connection. Atomic: hands out a session, knows no node/edge schema — that's graph_db/, written by hand."""
from contextlib import contextmanager

from neo4j import GraphDatabase


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    @contextmanager
    def session(self):
        with self._driver.session() as session:
            yield session

    def close(self) -> None:
        self._driver.close()
