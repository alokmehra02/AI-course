"""
Lesson 3 — Text-to-SQL with guardrails (manual implementation).

Demonstrates: schema injection, LLM SQL generation, AST validation (SELECT-only),
read-only execution pattern, self-correction loop (max 2 retries).

Requires: OPENAI_API_KEY, optional DATABASE_URL (defaults to SQLite in-memory demo).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("text_to_sql")

# ---------------------------------------------------------------------------
# Demo schema (replace with SQLAlchemy inspector against real DB in production)
# ---------------------------------------------------------------------------
DEMO_DDL = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, created_at TEXT);
INSERT INTO customers VALUES (1, 'Alice', 'a@example.com');
INSERT INTO customers VALUES (2, 'Bob', 'b@example.com');
INSERT INTO orders VALUES (1, 1, 150.0, '2026-01-15');
INSERT INTO orders VALUES (2, 1, 75.5, '2026-02-01');
INSERT INTO orders VALUES (3, 2, 200.0, '2026-02-10');
"""

BLOCKED_KEYWORDS = {"drop", "delete", "update", "insert", "alter", "truncate", "grant", "create"}


def validate_sql_select_only(sql: str) -> str:
    """Minimal guardrail — production should use sqlglot AST parsing."""
    normalized = sql.strip().lower().rstrip(";")
    if not normalized.startswith("select"):
        raise ValueError("Only SELECT statements are allowed")
    for kw in BLOCKED_KEYWORDS:
        if f" {kw} " in f" {normalized} ":
            raise ValueError(f"Forbidden keyword: {kw}")
    if ";" in normalized:
        raise ValueError("Multiple statements not allowed")
    return sql.strip()


def run_query(conn: sqlite3.Connection, sql: str, limit: int = 100) -> list[dict[str, Any]]:
    sql = validate_sql_select_only(sql)
    if "limit" not in sql.lower():
        sql = f"{sql.rstrip(';')} LIMIT {limit}"
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description or []]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


async def generate_sql(client: httpx.AsyncClient, question: str, ddl: str, error: str | None = None) -> str:
    system = (
        "You are a SQLite expert. Return ONLY a single SELECT query, no markdown. "
        "Use only tables from the schema below.\n\n" + ddl
    )
    user = question if not error else f"{question}\n\nPrevious query failed: {error}\nFix the SQL."
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    r = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json=payload,
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


async def text_to_sql(question: str, ddl: str = DEMO_DDL, max_retries: int = 2) -> dict[str, Any]:
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)
    error: str | None = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            sql = await generate_sql(client, question, ddl, error)
            logger.info("Attempt %s SQL: %s", attempt + 1, sql)
            try:
                rows = run_query(conn, sql)
                return {"sql": sql, "rows": rows, "attempts": attempt + 1}
            except Exception as e:
                error = str(e)
                logger.warning("Execution failed: %s", error)
    return {"error": error, "attempts": max_retries + 1}


if __name__ == "__main__":
    import asyncio

    q = "How much did Alice spend in total on orders?"
    result = asyncio.run(text_to_sql(q))
    print(json.dumps(result, indent=2, default=str))
