import csv
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import urllib.parse
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "financeiro.db"
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
SUPERADMIN_USERNAME = "krisrosa"
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "admin123")

DEFAULT_CATEGORIES = [
    "Mercado",
    "Energia",
    "Agua",
    "Internet",
    "Aluguel",
    "Cartao de credito",
    "Emprestimo",
    "Salario",
    "Servico",
    "Outros",
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def verify_password(password, salt, password_hash):
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                profile TEXT NOT NULL DEFAULT 'usuario',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Pendente', 'Pago', 'Vencido')),
                payment_method TEXT,
                notes TEXT,
                payment_date TEXT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS incomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                receipt_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Recebido', 'Pendente')),
                notes TEXT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )
        ensure_user_columns(conn)
        ensure_financial_columns(conn)
        for category in DEFAULT_CATEGORIES:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (category,))

        user = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not user:
            salt, password_hash = hash_password("admin123")
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, salt, profile, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("admin", "Administrador", password_hash, salt, "admin", 1, now()),
            )
        else:
            conn.execute("UPDATE users SET profile = 'admin', active = 1 WHERE username = 'admin'")

        superadmin = conn.execute("SELECT id FROM users WHERE username = ?", (SUPERADMIN_USERNAME,)).fetchone()
        if not superadmin:
            salt, password_hash = hash_password(SUPERADMIN_PASSWORD)
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, salt, profile, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (SUPERADMIN_USERNAME, "Kris Rosa", password_hash, salt, "superadmin", 1, now()),
            )
        else:
            conn.execute(
                "UPDATE users SET profile = 'superadmin', active = 1 WHERE username = ?",
                (SUPERADMIN_USERNAME,),
            )

        admin_id = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()["id"]
        conn.execute("UPDATE expenses SET user_id = ? WHERE user_id IS NULL", (admin_id,))
        conn.execute("UPDATE incomes SET user_id = ? WHERE user_id IS NULL", (admin_id,))


def ensure_user_columns(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "full_name" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
    if "profile" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN profile TEXT NOT NULL DEFAULT 'usuario'")
    if "active" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


def ensure_financial_columns(conn):
    expense_columns = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)").fetchall()}
    income_columns = {row["name"] for row in conn.execute("PRAGMA table_info(incomes)").fetchall()}
    if "user_id" not in expense_columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER")
    if "user_id" not in income_columns:
        conn.execute("ALTER TABLE incomes ADD COLUMN user_id INTEGER")


def now():
    return datetime.now().replace(microsecond=0).isoformat()


def today_iso():
    return date.today().isoformat()


def month_range(year, month):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def parse_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def row_to_dict(row):
    return dict(row) if row else None


def public_user(row):
    data = row_to_dict(row)
    if not data:
        return None
    return {
        "id": data["id"],
        "username": data["username"],
        "full_name": data.get("full_name", ""),
        "profile": data.get("profile", "usuario"),
        "active": bool(data.get("active", 1)),
        "created_at": data.get("created_at"),
    }


def clean_money(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("Valor invalido")
    if amount < 0:
        raise ValueError("Valor nao pode ser negativo")
    return round(amount, 2)


def require_fields(data, fields):
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        raise ValueError("Campos obrigatorios: " + ", ".join(missing))


def parse_query(path):
    parsed = urllib.parse.urlparse(path)
    params = urllib.parse.parse_qs(parsed.query)
    return parsed.path, {k: v[0] for k, v in params.items() if v}


def filters_to_sql(params, kind):
    clauses = []
    values = []
    month = params.get("month")
    year = params.get("year")
    status = params.get("status")
    category = params.get("category")
    date_field = "due_date" if kind == "expenses" else "receipt_date"

    if month and year:
        start, end = month_range(int(year), int(month))
        clauses.append(f"{date_field} >= ? AND {date_field} < ?")
        values.extend([start, end])
    elif year:
        clauses.append(f"substr({date_field}, 1, 4) = ?")
        values.append(str(year))

    if status:
        clauses.append("status = ?")
        values.append(status)
    if category:
        clauses.append("category = ?")
        values.append(category)

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, values


def apply_user_scope(where, values, user):
    if user["profile"] == "superadmin":
        return where, values
    if where:
        where += " AND user_id = ?"
    else:
        where = " WHERE user_id = ?"
    values.append(user["id"])
    return where, values


def owned_update_suffix(user):
    if user["profile"] == "superadmin":
        return "", []
    return " AND user_id = ?", [user["id"]]


def normalize_overdue_expenses():
    with connect() as conn:
        conn.execute(
            """
            UPDATE expenses
            SET status = 'Vencido', updated_at = ?
            WHERE status = 'Pendente' AND due_date < ?
            """,
            (now(), today_iso()),
        )


def expense_payload(data, partial=False):
    if not partial:
        require_fields(data, ["description", "category", "amount", "due_date", "status"])
    status = data.get("status", "Pendente")
    if status not in ("Pendente", "Pago", "Vencido"):
        raise ValueError("Status de despesa invalido")
    return {
        "description": str(data.get("description", "")).strip(),
        "category": str(data.get("category", "")).strip(),
        "amount": clean_money(data.get("amount", 0)),
        "due_date": str(data.get("due_date", "")).strip(),
        "status": status,
        "payment_method": str(data.get("payment_method", "")).strip(),
        "notes": str(data.get("notes", "")).strip(),
        "payment_date": str(data.get("payment_date", "")).strip(),
    }


def income_payload(data, partial=False):
    if not partial:
        require_fields(data, ["description", "category", "amount", "receipt_date", "status"])
    status = data.get("status", "Pendente")
    if status not in ("Recebido", "Pendente"):
        raise ValueError("Status de receita invalido")
    return {
        "description": str(data.get("description", "")).strip(),
        "category": str(data.get("category", "")).strip(),
        "amount": clean_money(data.get("amount", 0)),
        "receipt_date": str(data.get("receipt_date", "")).strip(),
        "status": status,
        "notes": str(data.get("notes", "")).strip(),
    }


def user_payload(data, creating=False, public=False):
    fields = ["full_name", "username"]
    if not public:
        fields.append("profile")
    if creating:
        fields.append("password")
    require_fields(data, fields)
    full_name = str(data.get("full_name", "")).strip()
    username = str(data.get("username", "")).strip()
    profile = "usuario" if public else str(data.get("profile", "usuario")).strip()
    if profile not in ("admin", "usuario"):
        raise ValueError("Perfil invalido")
    active = 1 if str(data.get("active", "true")).lower() in ("1", "true", "sim", "on") else 0
    password = str(data.get("password", ""))
    if creating and len(password) < 6:
        raise ValueError("A senha deve ter pelo menos 6 caracteres")
    confirm_password = str(data.get("confirm_password", password))
    if creating and password != confirm_password:
        raise ValueError("Confirmacao de senha diferente da senha")
    return {"full_name": full_name, "username": username, "profile": profile, "active": active, "password": password}


class FinanceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, data, status=HTTPStatus.OK):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        self.send_json({"error": message}, status)

    def current_user(self):
        token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return None
        with connect() as conn:
            row = conn.execute(
                """
                SELECT users.id, users.username, users.full_name, users.profile, users.active, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at > ? AND users.active = 1
                """,
                (token, now()),
            ).fetchone()
            return public_user(row)

    def require_user(self):
        user = self.current_user()
        if not user:
            self.send_error_json("Login necessario", HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def require_superadmin(self):
        user = self.require_user()
        if not user:
            return None
        if user["profile"] != "superadmin":
            self.send_error_json("Acesso permitido somente para o SuperAdmin", HTTPStatus.FORBIDDEN)
            return None
        return user

    def do_GET(self):
        path, params = parse_query(self.path)
        try:
            if path == "/health":
                return self.send_json({"status": "ok"})
            if path.startswith("/api/"):
                if path == "/api/me":
                    user = self.require_user()
                    return user and self.send_json({"user": user})
                if path == "/api/users":
                    return self.handle_list_users()
                if path == "/api/categories":
                    return self.handle_categories()
                if path == "/api/dashboard":
                    return self.handle_dashboard(params)
                if path == "/api/expenses":
                    return self.handle_list_expenses(params)
                if path == "/api/incomes":
                    return self.handle_list_incomes(params)
                if path == "/api/report":
                    return self.handle_report(params)
                if path == "/api/report/export":
                    return self.handle_report_export(params)
                return self.send_error_json("Rota nao encontrada", HTTPStatus.NOT_FOUND)
            return super().do_GET()
        except Exception as exc:
            return self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        path, _ = parse_query(self.path)
        try:
            data = parse_body(self)
            if path == "/api/login":
                return self.handle_login(data)
            if path == "/api/register":
                return self.handle_register(data)
            if path == "/api/logout":
                return self.handle_logout()
            if path == "/api/change-password":
                return self.handle_change_password(data)
            if path == "/api/users":
                return self.handle_create_user(data)
            if path.startswith("/api/users/") and path.endswith("/password"):
                user_id = int(path.split("/")[3])
                return self.handle_admin_change_password(user_id, data)
            if path.startswith("/api/users/") and path.endswith("/toggle"):
                user_id = int(path.split("/")[3])
                return self.handle_toggle_user(user_id)
            if self.require_user() is None:
                return
            if path == "/api/expenses":
                return self.handle_create_expense(data)
            if path == "/api/incomes":
                return self.handle_create_income(data)
            if path.startswith("/api/expenses/") and path.endswith("/pay"):
                expense_id = int(path.split("/")[3])
                return self.handle_pay_expense(expense_id, data)
            return self.send_error_json("Rota nao encontrada", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            return self.send_error_json(str(exc))
        except Exception as exc:
            return self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self):
        path, _ = parse_query(self.path)
        try:
            if self.require_user() is None:
                return
            data = parse_body(self)
            if path.startswith("/api/users/"):
                return self.handle_update_user(int(path.split("/")[3]), data)
            if path.startswith("/api/expenses/"):
                return self.handle_update_expense(int(path.split("/")[3]), data)
            if path.startswith("/api/incomes/"):
                return self.handle_update_income(int(path.split("/")[3]), data)
            return self.send_error_json("Rota nao encontrada", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            return self.send_error_json(str(exc))
        except Exception as exc:
            return self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self):
        path, _ = parse_query(self.path)
        try:
            if self.require_user() is None:
                return
            if path.startswith("/api/users/"):
                return self.handle_delete_user(int(path.split("/")[3]))
            if path.startswith("/api/expenses/"):
                return self.handle_delete("expenses", int(path.split("/")[3]))
            if path.startswith("/api/incomes/"):
                return self.handle_delete("incomes", int(path.split("/")[3]))
            return self.send_error_json("Rota nao encontrada", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_login(self, data):
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not user or not user["active"] or not verify_password(password, user["salt"], user["password_hash"]):
                return self.send_error_json("Usuario ou senha invalidos", HTTPStatus.UNAUTHORIZED)
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(hours=SESSION_HOURS)).replace(microsecond=0).isoformat()
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expires_at),
            )
            self.send_json({"token": token, "user": public_user(user)})

    def handle_register(self, data):
        payload = user_payload(data, creating=True, public=True)
        salt, password_hash = hash_password(payload["password"])
        try:
            with connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, full_name, password_hash, salt, profile, active, created_at)
                    VALUES (?, ?, ?, ?, 'usuario', 1, ?)
                    """,
                    (payload["username"], payload["full_name"], password_hash, salt, now()),
                )
        except sqlite3.IntegrityError:
            return self.send_error_json("Usuario ja existe")
        self.send_json({"id": cur.lastrowid, "message": "Conta criada com sucesso. Faça login."}, HTTPStatus.CREATED)

    def handle_logout(self):
        token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.send_json({"ok": True})

    def handle_list_users(self):
        if self.require_superadmin() is None:
            return
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, username, full_name, profile, active, created_at FROM users ORDER BY username"
            ).fetchall()
        self.send_json({"users": [public_user(row) for row in rows]})

    def handle_create_user(self, data):
        if self.require_superadmin() is None:
            return
        payload = user_payload(data, creating=True)
        salt, password_hash = hash_password(payload["password"])
        try:
            with connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, full_name, password_hash, salt, profile, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["username"],
                        payload["full_name"],
                        password_hash,
                        salt,
                        payload["profile"],
                        payload["active"],
                        now(),
                    ),
                )
        except sqlite3.IntegrityError:
            return self.send_error_json("Usuario ja existe")
        self.send_json({"id": cur.lastrowid}, HTTPStatus.CREATED)

    def handle_update_user(self, user_id, data):
        if self.require_superadmin() is None:
            return
        payload = user_payload(data)
        with connect() as conn:
            existing = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            if not existing:
                return self.send_error_json("Usuario nao encontrado", HTTPStatus.NOT_FOUND)
            if existing["username"] == SUPERADMIN_USERNAME and payload["username"] != SUPERADMIN_USERNAME:
                return self.send_error_json("O SuperAdmin principal nao pode ser renomeado")
            profile = "superadmin" if existing["username"] == SUPERADMIN_USERNAME else payload["profile"]
            active = 1 if existing["username"] == SUPERADMIN_USERNAME else payload["active"]
            try:
                conn.execute(
                    "UPDATE users SET username = ?, full_name = ?, profile = ?, active = ? WHERE id = ?",
                    (payload["username"], payload["full_name"], profile, active, user_id),
                )
            except sqlite3.IntegrityError:
                return self.send_error_json("Usuario ja existe")
        self.send_json({"ok": True})

    def handle_admin_change_password(self, user_id, data):
        if self.require_superadmin() is None:
            return
        new_password = str(data.get("password", ""))
        if len(new_password) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres")
        salt, password_hash = hash_password(new_password)
        with connect() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (password_hash, salt, user_id),
            )
        if cur.rowcount == 0:
            return self.send_error_json("Usuario nao encontrado", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})

    def handle_toggle_user(self, user_id):
        if self.require_superadmin() is None:
            return
        with connect() as conn:
            user = conn.execute("SELECT username, active FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return self.send_error_json("Usuario nao encontrado", HTTPStatus.NOT_FOUND)
            if user["username"] == SUPERADMIN_USERNAME:
                return self.send_error_json("O SuperAdmin principal nao pode ser desativado")
            new_active = 0 if user["active"] else 1
            conn.execute("UPDATE users SET active = ? WHERE id = ?", (new_active, user_id))
            if not new_active:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        self.send_json({"ok": True, "active": bool(new_active)})

    def handle_delete_user(self, user_id):
        if self.require_superadmin() is None:
            return
        with connect() as conn:
            user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return self.send_error_json("Usuario nao encontrado", HTTPStatus.NOT_FOUND)
            if user["username"] == SUPERADMIN_USERNAME:
                return self.send_error_json("O SuperAdmin principal nao pode ser excluido")
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.send_json({"ok": True})

    def handle_change_password(self, data):
        user = self.require_user()
        if not user:
            return
        old_password = str(data.get("old_password", ""))
        new_password = str(data.get("new_password", ""))
        if len(new_password) < 6:
            raise ValueError("A nova senha deve ter pelo menos 6 caracteres")
        with connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            if not verify_password(old_password, row["salt"], row["password_hash"]):
                return self.send_error_json("Senha atual incorreta", HTTPStatus.UNAUTHORIZED)
            salt, password_hash = hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (password_hash, salt, user["id"]),
            )
        self.send_json({"ok": True})

    def handle_categories(self):
        if self.require_user() is None:
            return
        with connect() as conn:
            rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
        self.send_json({"categories": [row["name"] for row in rows]})

    def handle_dashboard(self, params):
        user = self.require_user()
        if user is None:
            return
        normalize_overdue_expenses()
        selected = dashboard_period(params)
        start, end = month_range(selected["year"], selected["month"])
        today = today_iso()
        scope_sql, scope_values = owned_update_suffix(user)
        with connect() as conn:
            expenses = conn.execute(
                f"SELECT * FROM expenses WHERE due_date >= ? AND due_date < ?{scope_sql} ORDER BY due_date",
                (start, end, *scope_values),
            ).fetchall()
            incomes = conn.execute(
                f"SELECT * FROM incomes WHERE receipt_date >= ? AND receipt_date < ?{scope_sql} ORDER BY receipt_date",
                (start, end, *scope_values),
            ).fetchall()
            upcoming = conn.execute(
                f"""
                SELECT * FROM expenses
                WHERE status != 'Pago' AND due_date >= ?{scope_sql}
                ORDER BY due_date LIMIT 6
                """,
                (today, *scope_values),
            ).fetchall()

        total_pending = sum(row["amount"] for row in expenses if row["status"] != "Pago")
        total_paid = sum(row["amount"] for row in expenses if row["status"] == "Pago")
        total_income = sum(row["amount"] for row in incomes)
        real_income = sum(row["amount"] for row in incomes if row["status"] == "Recebido")
        overdue = [row_to_dict(row) for row in expenses if row["status"] != "Pago" and row["due_date"] < today]
        self.send_json(
            {
                "period": selected,
                "cards": {
                    "total_pending": round(total_pending, 2),
                    "total_paid": round(total_paid, 2),
                    "total_income": round(total_income, 2),
                    "expected_balance": round(total_income - total_pending - total_paid, 2),
                    "real_balance": round(real_income - total_paid, 2),
                    "overdue_count": len(overdue),
                },
                "overdue": overdue[:6],
                "upcoming": [row_to_dict(row) for row in upcoming],
            }
        )

    def handle_list_expenses(self, params):
        user = self.require_user()
        if user is None:
            return
        normalize_overdue_expenses()
        where, values = filters_to_sql(params, "expenses")
        where, values = apply_user_scope(where, values, user)
        with connect() as conn:
            rows = conn.execute(f"SELECT * FROM expenses{where} ORDER BY due_date DESC, id DESC", values).fetchall()
        self.send_json({"expenses": [row_to_dict(row) for row in rows]})

    def handle_list_incomes(self, params):
        user = self.require_user()
        if user is None:
            return
        where, values = filters_to_sql(params, "incomes")
        where, values = apply_user_scope(where, values, user)
        with connect() as conn:
            rows = conn.execute(f"SELECT * FROM incomes{where} ORDER BY receipt_date DESC, id DESC", values).fetchall()
        self.send_json({"incomes": [row_to_dict(row) for row in rows]})

    def handle_create_expense(self, data):
        user = self.require_user()
        if user is None:
            return
        payload = expense_payload(data)
        stamp = now()
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO expenses
                (description, category, amount, due_date, status, payment_method, notes, payment_date, user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["description"],
                    payload["category"],
                    payload["amount"],
                    payload["due_date"],
                    payload["status"],
                    payload["payment_method"],
                    payload["notes"],
                    payload["payment_date"],
                    user["id"],
                    stamp,
                    stamp,
                ),
            )
        self.send_json({"id": cur.lastrowid}, HTTPStatus.CREATED)

    def handle_update_expense(self, expense_id, data):
        user = self.require_user()
        if user is None:
            return
        payload = expense_payload(data)
        scope_sql, scope_values = owned_update_suffix(user)
        with connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE expenses
                SET description = ?, category = ?, amount = ?, due_date = ?, status = ?,
                    payment_method = ?, notes = ?, payment_date = ?, updated_at = ?
                WHERE id = ?{scope_sql}
                """,
                (
                    payload["description"],
                    payload["category"],
                    payload["amount"],
                    payload["due_date"],
                    payload["status"],
                    payload["payment_method"],
                    payload["notes"],
                    payload["payment_date"],
                    now(),
                    expense_id,
                    *scope_values,
                ),
            )
        if cur.rowcount == 0:
            return self.send_error_json("Conta nao encontrada", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})

    def handle_pay_expense(self, expense_id, data):
        user = self.require_user()
        if user is None:
            return
        payment_date = str(data.get("payment_date") or today_iso()).strip()
        payment_method = str(data.get("payment_method", "")).strip()
        scope_sql, scope_values = owned_update_suffix(user)
        with connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE expenses
                SET status = 'Pago', payment_date = ?, payment_method = COALESCE(NULLIF(?, ''), payment_method), updated_at = ?
                WHERE id = ?{scope_sql}
                """,
                (payment_date, payment_method, now(), expense_id, *scope_values),
            )
        if cur.rowcount == 0:
            return self.send_error_json("Conta nao encontrada", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})

    def handle_create_income(self, data):
        user = self.require_user()
        if user is None:
            return
        payload = income_payload(data)
        stamp = now()
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO incomes
                (description, category, amount, receipt_date, status, notes, user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["description"],
                    payload["category"],
                    payload["amount"],
                    payload["receipt_date"],
                    payload["status"],
                    payload["notes"],
                    user["id"],
                    stamp,
                    stamp,
                ),
            )
        self.send_json({"id": cur.lastrowid}, HTTPStatus.CREATED)

    def handle_update_income(self, income_id, data):
        user = self.require_user()
        if user is None:
            return
        payload = income_payload(data)
        scope_sql, scope_values = owned_update_suffix(user)
        with connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE incomes
                SET description = ?, category = ?, amount = ?, receipt_date = ?, status = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?{scope_sql}
                """,
                (
                    payload["description"],
                    payload["category"],
                    payload["amount"],
                    payload["receipt_date"],
                    payload["status"],
                    payload["notes"],
                    now(),
                    income_id,
                    *scope_values,
                ),
            )
        if cur.rowcount == 0:
            return self.send_error_json("Receita nao encontrada", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})

    def handle_delete(self, table, row_id):
        user = self.require_user()
        if user is None:
            return
        scope_sql, scope_values = owned_update_suffix(user)
        with connect() as conn:
            cur = conn.execute(f"DELETE FROM {table} WHERE id = ?{scope_sql}", (row_id, *scope_values))
        if cur.rowcount == 0:
            return self.send_error_json("Registro nao encontrado", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})

    def handle_report(self, params):
        user = self.require_user()
        if user is None:
            return
        data = build_report(params, user)
        self.send_json(data)

    def handle_report_export(self, params):
        user = self.require_user()
        if user is None:
            return
        report = build_report(params, user)
        rows = [
            ["Resumo", "Valor"],
            ["Total de receitas", money_value(report["summary"]["total_income"])],
            ["Total de despesas", money_value(report["summary"]["total_expense"])],
            ["Saldo final", money_value(report["summary"]["final_balance"])],
            [],
            ["Tipo", "Descricao", "Categoria", "Valor", "Data", "Status", "Forma de pagamento", "Observacao"],
        ]
        for item in report["paid_expenses"]:
            rows.append(["Despesa paga", item["description"], item["category"], item["amount"], item["due_date"], item["status"], item.get("payment_method", ""), item.get("notes", "")])
        for item in report["pending_expenses"]:
            rows.append(["Despesa pendente", item["description"], item["category"], item["amount"], item["due_date"], item["status"], item.get("payment_method", ""), item.get("notes", "")])
        for item in report["incomes"]:
            rows.append(["Receita", item["description"], item["category"], item["amount"], item["receipt_date"], item["status"], "", item.get("notes", "")])

        text = csv_string(rows)
        payload = text.encode("utf-8-sig")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=relatorio-financeiro.csv")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def dashboard_period(params):
    today = date.today()
    return {
        "month": int(params.get("month") or today.month),
        "year": int(params.get("year") or today.year),
    }


def build_report(params, user):
    normalize_overdue_expenses()
    selected = dashboard_period(params)
    start, end = month_range(selected["year"], selected["month"])
    movement_type = params.get("type", "")
    scope_sql, scope_values = owned_update_suffix(user)
    with connect() as conn:
        expenses = [] if movement_type == "Receita" else [row_to_dict(row) for row in conn.execute(
            f"SELECT * FROM expenses WHERE due_date >= ? AND due_date < ?{scope_sql} ORDER BY due_date, id",
            (start, end, *scope_values),
        ).fetchall()]
        incomes = [] if movement_type == "Despesa" else [row_to_dict(row) for row in conn.execute(
            f"SELECT * FROM incomes WHERE receipt_date >= ? AND receipt_date < ?{scope_sql} ORDER BY receipt_date, id",
            (start, end, *scope_values),
        ).fetchall()]

    total_income = sum(item["amount"] for item in incomes)
    total_expense = sum(item["amount"] for item in expenses)
    paid_expenses = [item for item in expenses if item["status"] == "Pago"]
    pending_expenses = [item for item in expenses if item["status"] != "Pago"]
    return {
        "period": selected,
        "summary": {
            "total_income": round(total_income, 2),
            "total_expense": round(total_expense, 2),
            "final_balance": round(total_income - total_expense, 2),
        },
        "incomes": incomes,
        "paid_expenses": paid_expenses,
        "pending_expenses": pending_expenses,
    }


def money_value(value):
    return f"{float(value):.2f}"


def csv_string(rows):
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerows(rows)
    return output.getvalue()


def run():
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), FinanceHandler)
    print(f"Sistema financeiro rodando em http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
