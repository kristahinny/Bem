import os
import sqlite3
import sys
from pathlib import Path

import server


ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = Path(os.environ.get("SQLITE_DB_PATH", ROOT / "data" / "financeiro.db"))


def sqlite_rows(conn, table):
    if not table_exists(conn, table):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def table_exists(conn, table):
    row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


def has_column(conn, table, column):
    return column in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def target_user_id(conn, username):
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return row["id"] if row else None


def migrate_users(source, target):
    mapping = {}
    for row in sqlite_rows(source, "users"):
        existing_id = target_user_id(target, row["username"])
        if existing_id:
            mapping[row["id"]] = existing_id
            continue
        cur = target.execute(
            """
            INSERT INTO users (username, full_name, password_hash, salt, profile, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["username"],
                row.get("full_name") or "",
                row["password_hash"],
                row["salt"],
                row.get("profile") or "usuario",
                row.get("active", 1),
                row.get("created_at") or server.now(),
            ),
        )
        mapping[row["id"]] = cur.lastrowid
    return mapping


def migrate_categories(source, target):
    for row in sqlite_rows(source, "categories"):
        target.execute(
            "INSERT INTO categories (name, active) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
            (row["name"], row.get("active", 1)),
        )


def duplicate_expense(target, row, user_id):
    return target.execute(
        """
        SELECT id FROM expenses
        WHERE user_id = ? AND description = ? AND category = ? AND amount = ? AND due_date = ?
        LIMIT 1
        """,
        (user_id, row["description"], row["category"], row["amount"], row["due_date"]),
    ).fetchone()


def duplicate_income(target, row, user_id):
    return target.execute(
        """
        SELECT id FROM incomes
        WHERE user_id = ? AND description = ? AND category = ? AND amount = ? AND receipt_date = ?
        LIMIT 1
        """,
        (user_id, row["description"], row["category"], row["amount"], row["receipt_date"]),
    ).fetchone()


def duplicate_goal(target, row, user_id):
    return target.execute(
        """
        SELECT id FROM goals
        WHERE user_id = ? AND name = ? AND target_amount = ? AND COALESCE(target_date, '') = COALESCE(?, '')
        LIMIT 1
        """,
        (user_id, row["name"], row["target_amount"], row.get("target_date")),
    ).fetchone()


def migrate_expenses(source, target, user_map):
    migrated = 0
    for row in sqlite_rows(source, "expenses"):
        user_id = user_map.get(row.get("user_id"))
        if not user_id or duplicate_expense(target, row, user_id):
            continue
        target.execute(
            """
            INSERT INTO expenses
            (description, category, amount, due_date, status, payment_method, notes, payment_date,
             user_id, installment_group, installment_number, installment_total, cancelled, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["description"],
                row["category"],
                row["amount"],
                row["due_date"],
                row["status"],
                row.get("payment_method"),
                row.get("notes"),
                row.get("payment_date"),
                user_id,
                row.get("installment_group"),
                row.get("installment_number"),
                row.get("installment_total"),
                row.get("cancelled", 0),
                row.get("active", 1) if "active" in row else 1,
                row.get("created_at") or server.now(),
                row.get("updated_at") or server.now(),
            ),
        )
        migrated += 1
    return migrated


def migrate_incomes(source, target, user_map):
    migrated = 0
    for row in sqlite_rows(source, "incomes"):
        user_id = user_map.get(row.get("user_id"))
        if not user_id or duplicate_income(target, row, user_id):
            continue
        target.execute(
            """
            INSERT INTO incomes
            (description, category, amount, receipt_date, status, notes, user_id, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["description"],
                row["category"],
                row["amount"],
                row["receipt_date"],
                row["status"],
                row.get("notes"),
                user_id,
                row.get("active", 1) if "active" in row else 1,
                row.get("created_at") or server.now(),
                row.get("updated_at") or server.now(),
            ),
        )
        migrated += 1
    return migrated


def migrate_goals(source, target, user_map):
    if not table_exists(source, "goals"):
        return 0
    migrated = 0
    for row in sqlite_rows(source, "goals"):
        user_id = user_map.get(row.get("user_id"))
        if not user_id or duplicate_goal(target, row, user_id):
            continue
        target.execute(
            """
            INSERT INTO goals
            (user_id, name, description, target_amount, current_amount, target_date, status, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                row["name"],
                row.get("description"),
                row["target_amount"],
                row.get("current_amount", 0),
                row.get("target_date"),
                row.get("status") or "Ativa",
                row.get("active", 1) if has_column(source, "goals", "active") else 1,
                row.get("created_at") or server.now(),
                row.get("updated_at") or server.now(),
            ),
        )
        migrated += 1
    return migrated


def main():
    if not server.USE_POSTGRES:
        print("DATABASE_URL nao configurada. Defina a URL do PostgreSQL antes de migrar.", file=sys.stderr)
        return 1
    if not SQLITE_PATH.exists():
        print(f"Banco SQLite nao encontrado: {SQLITE_PATH}", file=sys.stderr)
        return 1

    server.init_db()
    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    try:
        with server.connect() as target:
            user_map = migrate_users(source, target)
            migrate_categories(source, target)
            expenses = migrate_expenses(source, target, user_map)
            incomes = migrate_incomes(source, target, user_map)
            goals = migrate_goals(source, target, user_map)
        print(f"Migracao concluida: usuarios={len(user_map)}, despesas={expenses}, receitas={incomes}, metas={goals}.")
        return 0
    finally:
        source.close()


if __name__ == "__main__":
    raise SystemExit(main())
