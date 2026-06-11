import json
import base64
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
        category_blocked = False
        try:
            request("GET", "/api/categories/manage", token=normal_login["token"])
        except urllib.error.HTTPError as exc:
            category_blocked = exc.code == 403
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
        safe_category = request("POST", "/api/categories", {"name": "Categoria Teste Seguro"}, super_token)
        categories_before = request("GET", "/api/categories/manage", token=super_token)
        request("PUT", f"/api/categories/{safe_category['id']}", {"name": "Categoria Teste Seguro Editada", "active": "true"}, super_token)
        request("DELETE", f"/api/categories/{safe_category['id']}", token=super_token)
        categories_after_delete = request("GET", "/api/categories/manage", token=super_token)
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
        installment = request(
            "POST",
            "/api/expenses",
            {
                "description": "Notebook",
                "category": "Cartão de Crédito",
                "amount": 3000,
                "due_date": "2026-06-20",
                "status": "Pendente",
                "is_installment": "Sim",
                "installment_total": 10,
                "first_due_date": "2026-06-20",
            },
            normal_login["token"],
        )
        goal = request(
            "POST",
            "/api/goals",
            {
                "name": "Moto",
                "description": "Meta de teste",
                "target_amount": 12000,
                "current_amount": 1000,
                "target_date": "2027-01-31",
                "status": "Ativa",
            },
            normal_login["token"],
        )
        request("POST", f"/api/goals/{goal['id']}/add", {"amount": 500}, normal_login["token"])
        goals = request("GET", "/api/goals", token=normal_login["token"])
        category = request("POST", "/api/categories", {"name": "Categoria Teste"}, super_token)
        managed_categories = request("GET", "/api/categories/manage", token=super_token)
        admin_login = request("POST", "/api/login", {"username": "admin_criado", "password": "admin123"})
        admin_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=admin_login["token"])
        request("POST", f"/api/expenses/{expense['id']}/pay", {"payment_date": "2026-06-09"}, normal_login["token"])
        template_bytes = request("GET", "/api/import/template", token=normal_login["token"])
        template_sheets = server.read_xlsx_workbook(template_bytes)
        expected_template_headers = {
            "DESPESAS": ["Data", "Descrição", "Categoria", "Valor", "Vencimento", "Status", "Observação"],
            "RECEITAS": ["Data", "Descrição", "Categoria", "Valor", "Observação"],
            "METAS": ["Nome", "Descrição", "Valor Objetivo", "Valor Atual", "Data Prevista"],
            "PARCELADAS": ["Descrição", "Categoria", "Valor Total", "Parcelas", "Data Primeira Parcela"],
        }
        for sheet_name, expected_headers in expected_template_headers.items():
            assert_true(template_sheets.get(sheet_name, [[]])[0] == expected_headers, f"cabecalho oficial invalido na aba {sheet_name}")
        official_template_payload = {"filename": "modelo-importacao-financeira.xlsx", "content_base64": base64.b64encode(template_bytes).decode("ascii")}
        official_template_preview = request(
            "POST",
            "/api/import/preview",
            official_template_payload,
            normal_login["token"],
        )
        import_workbook = server.build_xlsx(
            {
                "DESPESAS": [
                    ["Data", "Descrição", "Categoria", "Valor", "Vencimento", "Status", "Observação"],
                    ["2026-06-18", "Despesa importada", "Moradia", "100", "2026-06-20", "Pendente", ""],
                    ["", "", "", "", "", "", ""],
                ],
                "RECEITAS": [
                    ["Data", "DESCRIÇÃO", "Categoria", "Valor", "Observação"],
                    ["2026-06-21", "Receita importada", "Outros", "200", ""],
                ],
                "METAS": [
                    ["Nome", "Descricao", "Valor Objetivo", "Valor Atual", "Data Prevista"],
                    ["Meta importada", "Teste de meta", "1000", "100", "2026-12-31"],
                ],
                "PARCELADAS": [
                    ["Descricao", "Categoria", "Valor Total", "Parcelas", "Data Primeira Parcela"],
                    ["Compra parcelada importada", "Cartao de Credito", "600", "2", "2026-06-25"],
                ],
            }
        )
        workbook_payload = {"filename": "modelo-importacao-financeira.xlsx", "content_base64": base64.b64encode(import_workbook).decode("ascii")}
        preview = request(
            "POST",
            "/api/import/preview",
            workbook_payload,
            normal_login["token"],
        )
        committed = request("POST", "/api/import/commit", {"rows": preview["valid"]}, normal_login["token"])
        duplicate_commit = request("POST", "/api/import/commit", {"rows": preview["valid"]}, normal_login["token"])
        request("DELETE", f"/api/expenses/{expense['id']}", token=normal_login["token"])
        after_soft_delete_expenses = request("GET", "/api/expenses?month=6&year=2026", token=normal_login["token"])
        normal_expenses = request("GET", "/api/expenses?month=6&year=2026", token=normal_login["token"])
        normal_incomes = request("GET", "/api/incomes?month=6&year=2026", token=normal_login["token"])
        normal_goals = request("GET", "/api/goals", token=normal_login["token"])
        admin_expenses = request("GET", "/api/expenses?month=6&year=2026", token=admin_login["token"])
        admin_incomes = request("GET", "/api/incomes?month=6&year=2026", token=admin_login["token"])
        request("DELETE", f"/api/users/{created_admin['id']}", token=super_token)
        users_after_delete = request("GET", "/api/users", token=super_token)
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
        charts = request("GET", "/api/charts", token=normal_login["token"])
        cashflow = request("GET", "/api/cashflow", token=normal_login["token"])
        csv_bytes = request("GET", "/api/report/export?month=6&year=2026", token=normal_login["token"])
        request("DELETE", f"/api/categories/{category['id']}", token=super_token)

        assert_true(super_login["user"]["profile"] == "superadmin", "login superadmin falhou")
        assert_true(normal_login["user"]["profile"] == "usuario", "cadastro publico nao criou usuario comum")
        assert_true(duplicate_blocked, "usuario duplicado nao foi bloqueado")
        assert_true(blocked, "usuario comum acessou menu/rota de usuarios")
        assert_true(category_blocked, "usuario comum acessou rota administrativa de categorias")
        assert_true(any(item["id"] == safe_category["id"] and item["active"] == 0 for item in categories_after_delete["categories"]), "categoria foi apagada em vez de desativada")
        assert_true(any(item["name"] == "Categoria Teste Seguro" for item in categories_before["categories"]), "categoria nao foi criada/listada")
        assert_true(set(template_sheets.keys()) >= {"DESPESAS", "RECEITAS", "METAS", "PARCELADAS"}, "modelo XLSX nao possui as abas oficiais")
        assert_true(official_template_preview["errors"] == [] and len(official_template_preview["valid"]) == 4, "modelo oficial XLSX nao passou na previa")
        assert_true(preview["errors"] == [] and len(preview["valid"]) == 4, "preview de importacao XLSX falhou")
        assert_true(committed["imported"] == 5, "importacao XLSX nao inseriu despesas, receitas, metas e parcelas")
        assert_true(duplicate_commit["imported"] == 0 and duplicate_commit["skipped"] == 4, "importacao duplicada nao foi ignorada")
        assert_true(not any(item["id"] == expense["id"] for item in after_soft_delete_expenses["expenses"]), "despesa desativada continuou na listagem")
        assert_true(any(item["id"] == created_admin["id"] and item["active"] is False for item in users_after_delete["users"]), "usuario foi apagado em vez de desativado")
        assert_true(any(item["description"] == "Despesa importada" for item in normal_expenses["expenses"]), "despesa importada nao apareceu para o usuario")
        assert_true(any(item["description"] == "Compra parcelada importada (1/2)" for item in normal_expenses["expenses"]), "parcela importada nao apareceu para o usuario")
        assert_true(any(item["id"] == income["id"] for item in normal_incomes["incomes"]), "receita cadastrada nao apareceu para o usuario")
        assert_true(any(item["name"] == "Meta importada" for item in normal_goals["goals"]), "meta importada nao apareceu para o usuario")
        assert_true(not admin_expenses["expenses"], "admin sem lancamentos viu contas de outro usuario")
        assert_true(not admin_incomes["incomes"], "admin sem lancamentos viu receitas de outro usuario")
        assert_true(any(item["description"] == "Despesa importada" for item in super_expenses["expenses"]), "superadmin nao viu todos os registros")
        assert_true(any(item["description"] == "Despesa importada" for item in filtered_super_expenses["expenses"]), "filtro por usuario do superadmin nao retornou a conta")
        assert_true(filtered_super_dashboard["cards"]["total_income"] == dashboard["cards"]["total_income"], "dashboard filtrado do superadmin divergiu do usuario")
        assert_true(filtered_super_report["summary"]["final_balance"] == report["summary"]["final_balance"], "relatorio filtrado do superadmin divergiu do usuario")
        assert_true(len(charts["months"]) == 12 and len(cashflow["cashflow"]) == 12, "graficos ou fluxo futuro nao retornaram 12 meses")
        print(
            json.dumps(
                {
                    "super_login": super_login["user"]["username"],
                    "super_profile": super_login["user"]["profile"],
                    "public_user_id": public_user["id"],
                    "duplicate_blocked": duplicate_blocked,
                    "created_admin_id": created_admin["id"],
                    "category_soft_deleted": True,
                    "user_soft_deleted": True,
                    "imported": committed["imported"],
                    "duplicate_import_skipped": duplicate_commit["skipped"],
                    "xlsx_template_bytes": len(template_bytes),
                    "normal_login": normal_login["user"]["username"],
                    "normal_profile": normal_login["user"]["profile"],
                    "normal_user_blocked_from_users": blocked,
                    "normal_expenses_count": len(normal_expenses["expenses"]),
                    "normal_incomes_count": len(normal_incomes["incomes"]),
                    "installments_created": installment["installments"],
                    "goals_count": len(goals["goals"]),
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
