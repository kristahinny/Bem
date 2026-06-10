import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["DATA_DIR"] = str(ROOT / "work" / "test-data")

import server  # noqa: E402


def request(method, path, data=None, token=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:8765{path}", data=body, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=5) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    shutil.rmtree(ROOT / "work" / "test-data", ignore_errors=True)
    server.init_db()
    httpd = ThreadingHTTPServer(("127.0.0.1", 8765), server.FinanceHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        super_login = request("POST", "/api/login", {"username": "krisrosa", "password": "admin123"})
        super_token = super_login["token"]
        public_user = request(
            "POST",
            "/api/register",
            {
                "full_name": "Usuario Publico",
                "username": "usuario_publico",
                "password": "usuario123",
                "confirm_password": "usuario123",
                "profile": "admin",
            },
        )
        duplicate_blocked = False
        try:
            request(
                "POST",
                "/api/register",
                {
                    "full_name": "Usuario Publico",
                    "username": "usuario_publico",
                    "password": "usuario123",
                    "confirm_password": "usuario123",
                },
            )
        except urllib.error.HTTPError as exc:
            duplicate_blocked = exc.code == 400

        normal_login = request("POST", "/api/login", {"username": "usuario_publico", "password": "usuario123"})
        blocked = False
        try:
            request("GET", "/api/users", token=normal_login["token"])
        except urllib.error.HTTPError as exc:
            blocked = exc.code == 403
        created_admin = request(
            "POST",
            "/api/users",
            {
                "full_name": "Admin Criado",
                "username": "admin_criado",
                "password": "admin123",
                "profile": "admin",
                "active": "true",
            },
            super_token,
        )
        expense = request(
            "POST",
            "/api/expenses",
            {
                "description": "Energia teste",
                "category": "Energia",
                "amount": 220.50,
                "due_date": "2026-06-15",
                "status": "Pendente",
                "payment_method": "Pix",
                "notes": "Teste automatico",
            },
            normal_login["token"],
        )
        income = request(
            "POST",
            "/api/incomes",
            {
                "description": "Salario teste",
                "category": "Salario",
                "amount": 3500,
                "receipt_date": "2026-06-05",
                "status": "Recebido",
                "notes": "Teste automatico",
            },
            normal_login["token"],
        )
        admin_login = request("POST", "/api/login", {"username": "admin_criado", "password": "admin123"})
        admin_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=admin_login["token"])
        request("POST", f"/api/expenses/{expense['id']}/pay", {"payment_date": "2026-06-09"}, normal_login["token"])
        normal_expenses = request("GET", "/api/expenses?month=6&year=2026", token=normal_login["token"])
        normal_incomes = request("GET", "/api/incomes?month=6&year=2026", token=normal_login["token"])
        admin_expenses = request("GET", "/api/expenses?month=6&year=2026", token=admin_login["token"])
        admin_incomes = request("GET", "/api/incomes?month=6&year=2026", token=admin_login["token"])
        super_expenses = request("GET", "/api/expenses?month=6&year=2026", token=super_token)
        filtered_super_expenses = request(
            "GET",
            f"/api/expenses?month=6&year=2026&user_id={public_user['id']}",
            token=super_token,
        )
        dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        super_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=super_token)
        filtered_super_dashboard = request(
            "GET",
            f"/api/dashboard?month=6&year=2026&user_id={public_user['id']}",
            token=super_token,
        )
        report = request("GET", "/api/report?month=6&year=2026", token=normal_login["token"])
        filtered_super_report = request(
            "GET",
            f"/api/report?month=6&year=2026&user_id={public_user['id']}",
            token=super_token,
        )
        csv_bytes = request("GET", "/api/report/export?month=6&year=2026", token=normal_login["token"])

        assert_true(super_login["user"]["profile"] == "superadmin", "login superadmin falhou")
        assert_true(normal_login["user"]["profile"] == "usuario", "cadastro publico nao criou usuario comum")
        assert_true(duplicate_blocked, "usuario duplicado nao foi bloqueado")
        assert_true(blocked, "usuario comum acessou menu/rota de usuarios")
        assert_true(any(item["id"] == expense["id"] for item in normal_expenses["expenses"]), "conta cadastrada nao apareceu para o usuario")
        assert_true(any(item["id"] == income["id"] for item in normal_incomes["incomes"]), "receita cadastrada nao apareceu para o usuario")
        assert_true(not admin_expenses["expenses"], "admin sem lancamentos viu contas de outro usuario")
        assert_true(not admin_incomes["incomes"], "admin sem lancamentos viu receitas de outro usuario")
        assert_true(any(item["id"] == expense["id"] for item in super_expenses["expenses"]), "superadmin nao viu todos os registros")
        assert_true(any(item["id"] == expense["id"] for item in filtered_super_expenses["expenses"]), "filtro por usuario do superadmin nao retornou a conta")
        assert_true(filtered_super_dashboard["cards"]["total_income"] == dashboard["cards"]["total_income"], "dashboard filtrado do superadmin divergiu do usuario")
        assert_true(filtered_super_report["summary"]["final_balance"] == report["summary"]["final_balance"], "relatorio filtrado do superadmin divergiu do usuario")
        print(
            json.dumps(
                {
                    "super_login": super_login["user"]["username"],
                    "super_profile": super_login["user"]["profile"],
                    "public_user_id": public_user["id"],
                    "duplicate_blocked": duplicate_blocked,
                    "created_admin_id": created_admin["id"],
                    "normal_login": normal_login["user"]["username"],
                    "normal_profile": normal_login["user"]["profile"],
                    "normal_user_blocked_from_users": blocked,
                    "normal_expenses_count": len(normal_expenses["expenses"]),
                    "normal_incomes_count": len(normal_incomes["incomes"]),
                    "admin_expenses_count": len(admin_expenses["expenses"]),
                    "super_expenses_count": len(super_expenses["expenses"]),
                    "filtered_super_expenses_count": len(filtered_super_expenses["expenses"]),
                    "admin_created_sees_own_total": admin_dashboard["cards"]["total_income"],
                    "superadmin_sees_all_income": super_dashboard["cards"]["total_income"],
                    "expense_id": expense["id"],
                    "income_id": income["id"],
                    "total_paid": dashboard["cards"]["total_paid"],
                    "final_balance": report["summary"]["final_balance"],
                    "csv_bytes": len(csv_bytes),
                },
                ensure_ascii=False,
            )
        )
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
