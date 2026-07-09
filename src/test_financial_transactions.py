import os
import tempfile
import unittest

import database
import main


class FinancialTransactionsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def test_create_transaction_validates_and_reports_recent_rows(self):
        transaction_id = database.create_transaction(
            "2026-07-08",
            "income",
            "Membership Dues",
            "25.126",
            "July dues",
            "jira",
        )

        transaction = database.get_transaction(transaction_id)
        report = database.financial_report()

        self.assertEqual(transaction["transaction_date"], "2026-07-08")
        self.assertEqual(transaction["type"], "income")
        self.assertEqual(transaction["category"], "Membership Dues")
        self.assertEqual(transaction["amount"], 25.13)
        self.assertEqual(report["total_income"], 25.13)
        self.assertEqual(report["transactions"][0]["id"], transaction_id)

    def test_create_transaction_rejects_invalid_records(self):
        invalid_cases = [
            ("07/08/2026", "income", "Dues", 10, "YYYY-MM-DD"),
            ("2026-07-08", "transfer", "Dues", 10, "income or expense"),
            ("2026-07-08", "expense", "", 10, "Category"),
            ("2026-07-08", "expense", "Venue", 0, "positive"),
            ("2026-07-08", "expense", "Venue", "ten", "valid number"),
        ]

        for transaction_date, tx_type, category, amount, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    database.create_transaction(transaction_date, tx_type, category, amount)

    def test_financial_transaction_api_requires_admin_and_returns_created_row(self):
        payload = {
            "transaction_date": "2026-07-08",
            "type": "expense",
            "category": "Venue",
            "amount": 150,
            "description": "Monthly room rental",
        }

        self.assertEqual(self.client.post("/api/financial/transactions", json=payload).status_code, 302)

        self.login_admin()
        response = self.client.post("/api/financial/transactions", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["transaction"]["category"], "Venue")
        self.assertEqual(data["transaction"]["recorded_by"], "jira")

        list_response = self.client.get("/api/financial/transactions")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.get_json()["transactions"][0]["id"], data["transaction_id"])

    def test_financial_transaction_api_returns_validation_errors(self):
        self.login_admin()
        response = self.client.post(
            "/api/financial/transactions",
            json={"transaction_date": "bad", "type": "expense", "category": "Venue", "amount": 10},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("YYYY-MM-DD", response.get_json()["error"])

    def test_financial_report_generates_performance_metrics_and_summaries(self):
        database.create_transaction("2026-06-01", "income", "Dues", 500, "Member dues", "jira")
        database.create_transaction("2026-06-02", "expense", "Venue", 100, "Room", "jira")
        database.create_transaction("2026-06-03", "expense", "Catering", 75, "Snacks", "jira")
        database.upsert_budget("Venue", 100, "2026")

        report = database.financial_report()

        self.assertEqual(report["transaction_count"], 3)
        self.assertEqual(report["net_balance"], 325)
        self.assertEqual(report["expense_ratio"], 35)
        self.assertEqual(report["monthly"][0]["net"], 325)
        self.assertEqual(report["top_expense_category"]["label"], "Venue")
        self.assertEqual(report["largest_expense"]["category"], "Venue")
        self.assertEqual(report["budgets"][0]["utilization"], 100)
        self.assertEqual(report["budgets"][0]["status"], "over")
        self.assertTrue(any("Net balance" in summary for summary in report["summaries"]))

    def test_financial_report_api_and_csv_export_include_report_sections(self):
        database.create_transaction("2026-06-01", "income", "Dues", 500, "Member dues", "jira")
        database.create_transaction("2026-06-02", "expense", "Venue", 100, "Room", "jira")
        database.upsert_budget("Venue", 120, "2026")
        self.login_admin()

        response = self.client.get("/api/financial/report")
        self.assertEqual(response.status_code, 200)
        self.assertIn("summaries", response.get_json())

        csv_response = self.client.get("/api/financial/report.csv")
        body = csv_response.get_data(as_text=True)
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("summary,total_income,500.0,,,500.0", body)
        self.assertIn("monthly,2026-06,500.0,100.0,400.0,", body)
        self.assertIn("budget,Venue 2026,,100.0,,83.33", body)

    def test_budget_monitoring_categories_thresholds_and_alerts(self):
        budget_id = database.upsert_budget("Venue", 100, "2026", warning_threshold=50, critical_threshold=90)
        database.create_transaction("2026-06-02", "expense", "Venue", 75, "Room", "jira")

        report = database.financial_report()
        budget = report["budgets"][0]

        self.assertEqual(budget["id"], budget_id)
        self.assertEqual(budget["status"], "watch")
        self.assertEqual(budget["remaining"], 25)
        self.assertEqual(report["budget_categories"][0]["name"], "Venue")

        first = database.generate_budget_alerts(report)
        second = database.generate_budget_alerts(database.financial_report())

        self.assertEqual(first["count"], 1)
        self.assertEqual(first["alerts"][0]["alert_level"], "watch")
        self.assertEqual(second["count"], 0)
        notifications = database.list_notifications()
        self.assertEqual(notifications[0]["category"], "budget")
        self.assertIn("Budget watch", notifications[0]["title"])

    def test_budget_monitoring_api_upserts_budgets_and_generates_alerts(self):
        self.login_admin()
        response = self.client.post(
            "/api/financial/budgets",
            json={
                "category": "Catering",
                "allocated_amount": 100,
                "fiscal_period": "2026",
                "warning_threshold": 60,
                "critical_threshold": 80,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["budget"]["status"], "ok")

        database.create_transaction("2026-07-01", "expense", "Catering", 85, "Food", "jira")
        alerts = self.client.post("/api/financial/budget-alerts")

        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(alerts.get_json()["alerts"][0]["alert_level"], "over")
        budgets = self.client.get("/api/financial/budgets").get_json()
        self.assertEqual(budgets["budgets"][0]["status"], "over")
        self.assertEqual(budgets["categories"][0]["name"], "Catering")

    def test_budget_monitoring_rejects_invalid_budget_setup(self):
        with self.assertRaisesRegex(ValueError, "category"):
            database.upsert_budget("", 100, "2026")
        with self.assertRaisesRegex(ValueError, "valid number"):
            database.upsert_budget("Venue", "bad", "2026")
        with self.assertRaisesRegex(ValueError, "warning threshold"):
            database.upsert_budget("Venue", 100, "2026", warning_threshold=100, critical_threshold=80)


if __name__ == "__main__":
    unittest.main()
