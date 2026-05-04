"""Dialect-adaptive vector type: pgvector Vector on PostgreSQL, JSON on SQLite."""

from typing import List, Optional
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.engine import Dialect


class _VectorComparator(TypeDecorator.Comparator):
    """Expose pgvector distance operators on the column."""

    def cosine_distance(self, other):
        return self.expr.op("<=>")(other)

    def l2_distance(self, other):
        return self.expr.op("<->")(other)

    def inner_product(self, other):
        return self.expr.op("<#>")(other)


class VectorType(TypeDecorator):
    """Stores embeddings as pgvector on PG, falls back to JSON on SQLite."""

    impl = JSON
    cache_ok = True
    comparator_factory = _VectorComparator

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Optional[List[float]], dialect: Dialect):
        return value

    def process_result_value(self, value, dialect: Dialect):
        if value is None:
            return None
        if isinstance(value, str):
            import json
            return json.loads(value)
        return value
