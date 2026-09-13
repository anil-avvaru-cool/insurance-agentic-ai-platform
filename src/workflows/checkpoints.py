"""Checkpoint connections; PostgreSQL schema setup is a separate release step."""
from dataclasses import dataclass, field
import os

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver


@dataclass(frozen=True)
class Checkpoints:
    backend: str
    target: str = field(repr=False)

    def __post_init__(self):
        if self.backend not in ("sqlite", "postgres") or not self.target.strip():
            raise ValueError("Invalid checkpoint configuration")

    def connect(self):
        if self.backend == "postgres":
            return PostgresSaver.from_conn_string(self.target)
        return SqliteSaver.from_conn_string(self.target)

    def setup(self):
        with self.connect() as saver:
            saver.setup()


def configured_checkpoints():
    backend = os.environ["CHECKPOINT_BACKEND"]
    if backend == "sqlite":
        return Checkpoints(backend, os.environ["CHECKPOINT_DB_PATH"])
    if backend == "postgres":
        return Checkpoints(backend, os.environ["CHECKPOINT_POSTGRES_DSN"])
    raise ValueError("Unsupported checkpoint backend")


if __name__ == "__main__":
    configured_checkpoints().setup()
