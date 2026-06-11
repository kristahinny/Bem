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
        super_login = request("POST", "/api/login", {"username": "admin", "password": "admin123"})
        super_token = super_login["token"]
        super_delete_blocked = False
        try:
            request("DELETE", f"/api/users/{super_login['user']['id']}", token=super_token)
        except urllib.error.HTTPError as exc:
            super_delete_blocked = exc.code == 400
        super_toggle_blocked = False
        try:
            request("POST", f"/api/users/{super_login['user']['id']}/toggle", {}, super_token)
        except urllib.error.HTTPError as exc:
            super_toggle_blocked = exc.code == 400
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
        income_to_delete = request(
            "POST",
            "/api/incomes",
            {
                "description": "Receita para excluir",
                "category": "Outros",
                "amount": 123,
                "receipt_date": "2026-06-11",
                "status": "Recebido",
                "notes": "Teste de exclusao",
            },
            normal_login["token"],
        )
        pending_income = request(
            "POST",
            "/api/incomes",
            {
                "description": "Receita pendente teste",
                "category": "Servico",
                "amount": 200,
                "receipt_date": "2026-06-22",
                "status": "Pendente",
                "notes": "Deve entrar no dashboard apenas ao receber",
            },
            normal_login["token"],
        )
        dashboard_before_receive_pending = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        request("POST", f"/api/incomes/{pending_income['id']}/receive", {}, normal_login["token"])
        dashboard_after_receive_pending = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        pending_income_filter_after_receive = request("GET", "/api/incomes?month=6&year=2026&status=Pendente", token=normal_login["token"])
        recurring_income = request(
            "POST",
            "/api/incomes",
            {
                "description": "Servico mensal",
                "category": "Outros",
                "amount": 500,
                "receipt_date": "2026-07-05",
                "status": "Pendente",
                "notes": "Recorrente automatico",
                "is_recurring": "Sim",
                "recurring_total": 12,
                "first_receipt_date": "2026-07-05",
                "recurring_amount": 500,
            },
            normal_login["token"],
        )
        installment = request(
            "POST",
            "/api/expenses",
            {
                "description": "Notebook",
                "category": "Cartão de Crédito",
                "amount": 300,
                "due_date": "2026-06-20",
                "status": "Pendente",
                "is_installment": "Sim",
                "installment_total": 10,
                "first_due_date": "2026-06-20",
            },
            normal_login["token"],
        )
        request(
            "PUT",
            f"/api/expenses/{installment['ids'][1]}",
            {
                "description": "Notebook (2/10)",
                "category": "Cartao de Credito",
                "amount": 250,
                "due_date": "2026-07-20",
                "status": "Pendente",
                "payment_method": "Cartao",
                "notes": "Parcela ajustada",
                "update_scope": "single",
            },
            normal_login["token"],
        )
        future_after_installment = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])["cards"]["future_installments"]
        request("POST", f"/api/expenses/{installment['ids'][1]}/pay", {"payment_date": "2026-07-20"}, normal_login["token"])
        future_after_paid = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])["cards"]["future_installments"]
        cancel_installments = request("POST", f"/api/expenses/{installment['ids'][0]}/cancel-future", {}, normal_login["token"])
        future_after_cancel_installments = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])["cards"]["future_installments"]
        nubank_three = request(
            "POST",
            "/api/expenses",
            {
                "description": "Cartao Nubank",
                "category": "Cartao de Credito",
                "amount": 11.50,
                "due_date": "2026-07-10",
                "status": "Pendente",
                "is_installment": "Sim",
                "installment_total": 3,
                "first_due_date": "2026-07-10",
            },
            normal_login["token"],
        )
        nubank_two = request(
            "POST",
            "/api/expenses",
            {
                "description": "Cartao Nubank",
                "category": "Cartao de Credito",
                "amount": 53,
                "due_date": "2026-07-15",
                "status": "Pendente",
                "is_installment": "Sim",
                "installment_total": 2,
                "first_due_date": "2026-07-15",
            },
            normal_login["token"],
        )
        request(
            "PUT",
            f"/api/expenses/{nubank_three['ids'][1]}",
            {
                "description": "Cartao Nubank (2/3)",
                "category": "Cartao de Credito",
                "amount": 10,
                "due_date": "2026-08-10",
                "status": "Pendente",
                "notes": "Parcela ajustada individualmente",
                "update_scope": "single",
            },
            normal_login["token"],
        )
        request(
            "PUT",
            f"/api/incomes/{recurring_income['ids'][1]}",
            {
                "description": "Servico mensal (2/12)",
                "category": "Outros",
                "amount": 400,
                "receipt_date": "2026-08-05",
                "status": "Pendente",
                "notes": "Recebimento parcial previsto",
                "update_scope": "single",
            },
            normal_login["token"],
        )
        request("POST", f"/api/incomes/{recurring_income['ids'][1]}/receive", {}, normal_login["token"])
        recurring_pending_after_receive = request("GET", "/api/incomes?year=2026&status=Pendente", token=normal_login["token"])
        cancel_recurring = request("POST", f"/api/incomes/{recurring_income['ids'][1]}/cancel-future", {}, normal_login["token"])
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
        deleted_goal = request(
            "POST",
            "/api/goals",
            {
                "name": "Meta para excluir",
                "description": "Nao deve aparecer no dashboard",
                "target_amount": 5000,
                "current_amount": 777,
                "target_date": "2026-12-31",
                "status": "Ativa",
            },
            normal_login["token"],
        )
        request("POST", f"/api/goals/{goal['id']}/add", {"amount": 500}, normal_login["token"])
        goals = request("GET", "/api/goals", token=normal_login["token"])
        category = request("POST", "/api/categories", {"name": "Categoria Teste"}, super_token)
        managed_categories = request("GET", "/api/categories/manage", token=super_token)
        normal_maintenance_blocked = False
        try:
            request("GET", "/api/maintenance", token=normal_login["token"])
        except urllib.error.HTTPError as exc:
            normal_maintenance_blocked = exc.code == 403
        maintenance_status = request("GET", "/api/maintenance", token=super_token)
        maintenance_settings = request(
            "PUT",
            "/api/maintenance/settings",
            {"cleanup_logs_days": 90, "import_history_days": 180, "temp_files_days": 30, "test_records_days": 30},
            super_token,
        )
        maintenance_run = request("POST", "/api/maintenance/run", {}, super_token)
        admin_login = request("POST", "/api/login", {"username": "admin_criado", "password": "admin123"})
        blocked_cross_delete = False
        try:
            request("DELETE", f"/api/incomes/{income['id']}", token=admin_login["token"])
        except urllib.error.HTTPError as exc:
            blocked_cross_delete = exc.code == 404
        admin_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=admin_login["token"])
        request("POST", f"/api/expenses/{expense['id']}/pay", {"payment_date": "2026-06-09"}, normal_login["token"])
        paid_expense_pending_filter = request("GET", "/api/expenses?month=6&year=2026&status=Pendente", token=normal_login["token"])
        template_bytes = request("GET", "/api/import/template", token=normal_login["token"])
        template_sheets = server.read_xlsx_workbook(template_bytes)
        expected_template_headers = {name: config["model_headers"] for name, config in server.IMPORT_SHEETS.items()}

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
                    server.IMPORT_SHEETS["RECEITAS"]["model_headers"],
                    ["2026-06-21", "Receita importada", "Outros", "200", "", "Sim", "3", "2026-06-21"],
                ],
                "METAS": [
                    ["Nome", "Descricao", "Valor Objetivo", "Valor Atual", "Data Prevista"],
                    ["Meta importada", "Teste de meta", "1000", "100", "2026-12-31"],
                ],
                "PARCELADAS": [
                    server.IMPORT_SHEETS["PARCELADAS"]["model_headers"],
                    ["Compra parcelada importada", "Cartao de Credito", "250", "2", "2026-06-25"],
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
        dashboard_before_goal_delete = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        request("DELETE", f"/api/expenses/{expense['id']}", token=normal_login["token"])
        request("DELETE", f"/api/expenses/{installment['ids'][0]}", token=normal_login["token"])
        request("DELETE", f"/api/incomes/{income_to_delete['id']}", token=normal_login["token"])
        delete_goal_response = request("DELETE", f"/api/goals/{deleted_goal['id']}", token=normal_login["token"])
        dashboard_after_goal_delete = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        after_soft_delete_expenses = request("GET", "/api/expenses?month=6&year=2026", token=normal_login["token"])
        normal_expenses = request("GET", "/api/expenses?month=6&year=2026", token=normal_login["token"])
        normal_incomes = request("GET", "/api/incomes?month=6&year=2026", token=normal_login["token"])
        july_expenses = request("GET", "/api/expenses?month=7&year=2026", token=normal_login["token"])
        year_expenses = request("GET", "/api/expenses?year=2026", token=normal_login["token"])
        year_incomes = request("GET", "/api/incomes?year=2026", token=normal_login["token"])
        normal_goals = request("GET", "/api/goals", token=normal_login["token"])
        admin_expenses = request("GET", "/api/expenses?month=6&year=2026", token=admin_login["token"])
        admin_incomes = request("GET", "/api/incomes?month=6&year=2026", token=admin_login["token"])
        delete_user_response = request("DELETE", f"/api/users/{created_admin['id']}", token=super_token)
        users_after_delete = request("GET", "/api/users", token=super_token)
        deleted_users = request("GET", "/api/users/deleted", token=super_token)
        deleted_login_blocked = False
        try:
            request("POST", "/api/login", {"username": "admin_criado", "password": "admin123"})
        except urllib.error.HTTPError as exc:
            deleted_login_blocked = exc.code == 401
        with server.connect() as conn:
            deleted_admin_row = conn.execute(
                "SELECT active, deleted, deleted_at, deleted_by FROM users WHERE id = ?",
                (created_admin["id"],),
            ).fetchone()
        restore_user_response = request("POST", f"/api/users/{created_admin['id']}/restore", {}, super_token)
        users_after_restore = request("GET", "/api/users", token=super_token)
        restored_login = request("POST", "/api/login", {"username": "admin_criado", "password": "admin123"})
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
        normal_financial_reset_blocked = False
        try:
            request("POST", "/api/maintenance/financial-reset", {"confirmation": "LIMPAR DADOS"}, normal_login["token"])
        except urllib.error.HTTPError as exc:
            normal_financial_reset_blocked = exc.code == 403
        financial_reset = request("POST", "/api/maintenance/financial-reset", {"confirmation": "LIMPAR DADOS"}, super_token)
        reset_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=normal_login["token"])
        reset_expenses = request("GET", "/api/expenses?year=2026", token=normal_login["token"])
        reset_incomes = request("GET", "/api/incomes?year=2026", token=normal_login["token"])
        reset_goals = request("GET", "/api/goals", token=normal_login["token"])
        reset_categories = request("GET", "/api/categories/manage", token=super_token)
        reset_users = request("GET", "/api/users", token=super_token)
        normal_system_reset_blocked = False
        try:
            request("POST", "/api/maintenance/system-reset", {"confirmation": "ZERAR SISTEMA"}, normal_login["token"])
        except urllib.error.HTTPError as exc:
            normal_system_reset_blocked = exc.code == 403
        system_reset = request("POST", "/api/maintenance/system-reset", {"confirmation": "ZERAR SISTEMA"}, super_token)
        system_token = system_reset["token"]
        system_dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=system_token)
        system_expenses = request("GET", "/api/expenses?year=2026", token=system_token)
        system_incomes = request("GET", "/api/incomes?year=2026", token=system_token)
        system_goals = request("GET", "/api/goals", token=system_token)
        system_users = request("GET", "/api/users", token=system_token)
        system_deleted_users = request("GET", "/api/users/deleted", token=system_token)
        system_categories = request("GET", "/api/categories/manage", token=system_token)
        removed_user_login_blocked = False
        try:
            request("POST", "/api/login", {"username": "usuario_publico", "password": "usuario123"})
        except urllib.error.HTTPError as exc:
            removed_user_login_blocked = exc.code == 401
        principal_login = request("POST", "/api/login", {"username": system_reset["user"]["username"], "password": "admin123"})

        assert_true(super_login["user"]["profile"] == "superadmin", "login superadmin falhou")
        assert_true(super_login["user"]["role"] == "superadmin" and super_login["user"]["active"] is True and super_login["user"]["deleted"] is False, "role/status do superadmin invalido")
        assert_true(super_delete_blocked, "SuperAdmin principal pode ser excluido")
        assert_true(super_toggle_blocked, "SuperAdmin principal pode ser desativado")
        assert_true(normal_login["user"]["profile"] == "usuario", "cadastro publico nao criou usuario comum")
        assert_true(duplicate_blocked, "usuario duplicado nao foi bloqueado")
        assert_true(blocked, "usuario comum acessou menu/rota de usuarios")
        assert_true(category_blocked, "usuario comum acessou rota administrativa de categorias")
        assert_true(blocked_cross_delete, "usuario conseguiu excluir dados de outro usuario")
        assert_true(any(item["id"] == safe_category["id"] and item["active"] == 0 for item in categories_after_delete["categories"]), "categoria foi apagada em vez de desativada")
        assert_true(any(item["name"] == "Categoria Teste Seguro" for item in categories_before["categories"]), "categoria nao foi criada/listada")
        assert_true(normal_maintenance_blocked, "usuario comum acessou manutencao")
        assert_true("settings" in maintenance_status and maintenance_settings["settings"]["cleanup_logs_days"] == 90, "configuracao de manutencao falhou")
        assert_true(len(maintenance_run["result"]["report"]) >= 4, "limpeza manual nao gerou relatorio")
        assert_true(
            dashboard_before_receive_pending["cards"]["total_income"] + 200 == dashboard_after_receive_pending["cards"]["total_income"],
            "receita pendente entrou no total antes de ser recebida ou nao atualizou ao receber",
        )
        assert_true(
            dashboard_before_receive_pending["cards"]["future_incomes"] - 200 == dashboard_after_receive_pending["cards"]["future_incomes"],
            "receita recebida continuou como receita futura",
        )
        assert_true(not any(item["id"] == pending_income["id"] for item in pending_income_filter_after_receive["incomes"]), "receita recebida continuou no filtro de pendentes")
        assert_true(future_after_installment == 2950.0, "parcelas futuras incluiu valor incorreto apos criar parcelamento")
        assert_true(future_after_paid == 2700.0, "parcela paga nao saiu de parcelas futuras")
        assert_true(cancel_installments["cancelled"] == 8 and future_after_cancel_installments == 300.0, "parcelas canceladas nao sairam de parcelas futuras")
        assert_true(not any(item["id"] == expense["id"] for item in paid_expense_pending_filter["expenses"]), "despesa paga continuou no filtro de pendentes")
        assert_true(set(template_sheets.keys()) >= {"DESPESAS", "RECEITAS", "METAS", "PARCELADAS"}, "modelo XLSX nao possui as abas oficiais")
        assert_true(official_template_preview["errors"] == [] and len(official_template_preview["valid"]) == 4, "modelo oficial XLSX nao passou na previa")
        assert_true(preview["errors"] == [] and len(preview["valid"]) == 4, "preview de importacao XLSX falhou")
        assert_true(committed["imported"] == 7, "importacao XLSX nao inseriu despesas, receitas recorrentes, metas e parcelas")
        assert_true(duplicate_commit["imported"] == 0 and duplicate_commit["skipped"] == 4, "importacao duplicada nao foi ignorada")
        assert_true(not any(item["id"] == expense["id"] for item in after_soft_delete_expenses["expenses"]), "despesa desativada continuou na listagem")
        assert_true(delete_goal_response["success"] is True, "DELETE nao retornou sucesso claro")
        assert_true(not any(item["id"] == income_to_delete["id"] for item in normal_incomes["incomes"]), "receita excluida continuou na listagem")
        assert_true(not any(item["id"] == deleted_goal["id"] for item in normal_goals["goals"]), "meta excluida continuou na listagem")
        assert_true(dashboard_after_goal_delete["cards"]["goals_total"] == dashboard_before_goal_delete["cards"]["goals_total"] - 777, "dashboard nao recalculou metas apos exclusao")
        assert_true(delete_user_response["message"] == "Usuário desativado com sucesso", "DELETE de usuario nao retornou mensagem correta")
        assert_true(not any(item["id"] == created_admin["id"] for item in users_after_delete["users"]), "usuario excluido continuou na listagem normal")
        assert_true(deleted_login_blocked, "usuario excluido conseguiu fazer login")
        assert_true(
            deleted_admin_row
            and int(deleted_admin_row["active"]) == 0
            and int(deleted_admin_row["deleted"]) == 1
            and deleted_admin_row["deleted_at"]
            and int(deleted_admin_row["deleted_by"]) == super_login["user"]["id"],
            "usuario excluido nao foi preservado com flags de exclusao logica",
        )
        assert_true(any(item["id"] == created_admin["id"] for item in deleted_users["users"]), "usuario excluido nao apareceu em Seguranca")
        assert_true(restore_user_response["success"] is True, "restauracao de usuario falhou")
        assert_true(any(item["id"] == created_admin["id"] for item in users_after_restore["users"]), "usuario restaurado nao voltou para a listagem")
        assert_true(restored_login["user"]["username"] == "admin_criado", "usuario restaurado nao conseguiu login")
        assert_true(any(item["description"] == "Despesa importada" for item in normal_expenses["expenses"]), "despesa importada nao apareceu para o usuario")
        assert_true(any(item["description"] == "Compra parcelada importada (1/2)" for item in normal_expenses["expenses"]), "parcela importada nao apareceu para o usuario")
        assert_true(any(item["description"] == "Notebook (2/10)" and float(item["amount"]) == 250 for item in july_expenses["expenses"]), "edicao individual de parcela de despesa falhou")
        nubank_three_rows = [item for item in year_expenses["expenses"] if item["id"] in nubank_three["ids"]]
        nubank_two_rows = [item for item in year_expenses["expenses"] if item["id"] in nubank_two["ids"]]
        assert_true(len(nubank_three_rows) == 3 and sorted(round(float(item["amount"]), 2) for item in nubank_three_rows) == [10.0, 11.5, 11.5], "parcelas de 11,50 nao foram geradas/editadas corretamente")
        assert_true(len(nubank_two_rows) == 2 and all(round(float(item["amount"]), 2) == 53.0 for item in nubank_two_rows), "parcelas de 53,00 nao foram geradas corretamente")
        assert_true(nubank_three_rows[0]["installment_group"] != nubank_two_rows[0]["installment_group"], "parcelamentos iguais foram agrupados indevidamente")
        assert_true(any(item["id"] == income["id"] for item in normal_incomes["incomes"]), "receita cadastrada nao apareceu para o usuario")
        assert_true(recurring_income["recurrences"] == 12 and cancel_recurring["cancelled"] == 10, "receita recorrente 12 meses ou cancelamento futuro falhou")
        assert_true(not any(item["id"] == recurring_income["ids"][1] for item in recurring_pending_after_receive["incomes"]), "receita recorrente recebida continuou no filtro de pendentes")
        assert_true(any(item["description"] == "Servico mensal (2/12)" and float(item["amount"]) == 400 and item["status"] == "Recebido" for item in year_incomes["incomes"]), "edicao individual ou recebimento de receita recorrente falhou")
        assert_true(not any(item["description"] == "Servico mensal (3/12)" for item in year_incomes["incomes"]), "receitas futuras canceladas continuaram na listagem")
        assert_true(any(item["description"] == "Receita importada (3/3)" for item in year_incomes["incomes"]), "importacao de receita recorrente nao gerou receitas futuras")
        assert_true(any(item["name"] == "Meta importada" for item in normal_goals["goals"]), "meta importada nao apareceu para o usuario")
        assert_true(not admin_expenses["expenses"], "admin sem lancamentos viu contas de outro usuario")
        assert_true(not admin_incomes["incomes"], "admin sem lancamentos viu receitas de outro usuario")
        assert_true(any(item["description"] == "Despesa importada" for item in super_expenses["expenses"]), "superadmin nao viu todos os registros")
        assert_true(any(item["description"] == "Despesa importada" for item in filtered_super_expenses["expenses"]), "filtro por usuario do superadmin nao retornou a conta")
        assert_true(filtered_super_dashboard["cards"]["total_income"] == dashboard["cards"]["total_income"], "dashboard filtrado do superadmin divergiu do usuario")
        assert_true(filtered_super_report["summary"]["final_balance"] == report["summary"]["final_balance"], "relatorio filtrado do superadmin divergiu do usuario")
        assert_true(len(charts["months"]) == 12 and len(cashflow["cashflow"]) == 12, "graficos ou fluxo futuro nao retornaram 12 meses")
        assert_true(normal_financial_reset_blocked, "usuario comum executou limpeza financeira administrativa")
        assert_true(financial_reset["success"] is True and financial_reset["result"]["total_removed"] > 0, "limpeza financeira nao removeu dados")
        assert_true(financial_reset["result"]["users_preserved"] >= 3, "limpeza financeira removeu usuarios")
        assert_true(reset_dashboard["cards"]["total_income"] == 0 and reset_dashboard["cards"]["total_expenses"] == 0 and reset_dashboard["cards"]["goals_total"] == 0, "dashboard nao zerou apos limpeza financeira")
        assert_true(not reset_expenses["expenses"] and not reset_incomes["incomes"] and not reset_goals["goals"], "dados financeiros continuaram nas listagens apos limpeza")
        assert_true(any(item["name"] == "Moradia" and item["active"] == 1 for item in reset_categories["categories"]), "categorias padrao nao foram preservadas")
        assert_true(not any(item["name"].startswith("Categoria Teste") for item in reset_categories["categories"]), "categorias personalizadas nao foram removidas")
        assert_true(any(item["id"] == public_user["id"] for item in reset_users["users"]), "usuarios nao foram preservados apos limpeza financeira")
        assert_true(normal_system_reset_blocked, "usuario comum executou zeragem completa")
        assert_true(system_reset["success"] is True and system_reset["message"] == "Sistema zerado com sucesso.", "zeragem completa nao retornou sucesso")
        assert_true(system_reset["result"]["users_preserved"] == 1, "zeragem completa preservou mais de um usuario")
        assert_true(len(system_users["users"]) == 1 and system_users["users"][0]["profile"] == "superadmin", "zeragem completa nao manteve apenas o superadmin")
        assert_true(not system_deleted_users["users"], "usuarios excluidos continuaram apos zeragem completa")
        assert_true(removed_user_login_blocked, "usuario comum continuou conseguindo login apos zeragem")
        assert_true(principal_login["user"]["profile"] == "superadmin", "admin/superadmin principal nao conseguiu login apos zeragem")
        assert_true(system_dashboard["cards"]["total_income"] == 0 and system_dashboard["cards"]["total_expenses"] == 0 and system_dashboard["cards"]["goals_total"] == 0, "dashboard nao zerou apos zeragem completa")
        assert_true(not system_expenses["expenses"] and not system_incomes["incomes"] and not system_goals["goals"], "dados financeiros continuaram apos zeragem completa")
        assert_true(any(item["name"] == "Moradia" and item["active"] == 1 for item in system_categories["categories"]), "categorias padrao nao foram recriadas apos zeragem")
        print(
            json.dumps(
                {
                    "super_login": super_login["user"]["username"],
                    "super_profile": super_login["user"]["profile"],
                    "public_user_id": public_user["id"],
                    "duplicate_blocked": duplicate_blocked,
                    "created_admin_id": created_admin["id"],
                    "category_soft_deleted": True,
                    "user_soft_deleted": delete_user_response["success"],
                    "deleted_user_login_blocked": deleted_login_blocked,
                    "user_restored": restore_user_response["success"],
                    "maintenance_items": len(maintenance_run["result"]["report"]),
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
                    "financial_reset_removed": financial_reset["result"]["total_removed"],
                    "financial_reset_users_preserved": financial_reset["result"]["users_preserved"],
                    "system_reset_removed": system_reset["result"]["total_removed"],
                    "system_reset_principal": system_reset["user"]["username"],
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

