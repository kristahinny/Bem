import json
import os
import sys
import threading
import time
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


def main():
    server.init_db()
    httpd = ThreadingHTTPServer(("127.0.0.1", 8765), server.FinanceHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        login = request("POST", "/api/login", {"username": "admin", "password": "admin123"})
        token = login["token"]
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
            token,
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
            token,
        )
        request("POST", f"/api/expenses/{expense['id']}/pay", {"payment_date": "2026-06-09"}, token)
        dashboard = request("GET", "/api/dashboard?month=6&year=2026", token=token)
        report = request("GET", "/api/report?month=6&year=2026", token=token)
        csv_bytes = request("GET", "/api/report/export?month=6&year=2026", token=token)
        print(
            json.dumps(
                {
                    "login": login["user"]["username"],
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
