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


if __name__ == "__main__":
    unittest.main()
