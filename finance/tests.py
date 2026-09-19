from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from .budgeting import (
    expected_income,
    pending_forecast,
    pending_outflows,
    posted_expenses,
    ready_to_assign,
    safe_cash,
    upcoming_bill_reserves,
)
from .models import (
    Account,
    BudgetAllocation,
    BudgetPeriod,
    BudgetSettings,
    Category,
    Envelope,
    Paycheck,
    RecurringBill,
    Transaction,
    PlaidItem,
)
from .plaid import decrypt_access_token, encrypt_access_token
from .sync import sync_item


class BudgetingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="budget-user",
            password="test-password",
        )
        self.cash = Account.objects.create(
            owner=self.user,
            institution_name="Test Bank",
            name="Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("1000.00"),
            plaid_account_identifier="item-checking",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.card = Account.objects.create(
            owner=self.user,
            institution_name="Test Bank",
            name="Card",
            account_type=Account.AccountType.CREDIT_CARD,
            current_balance=Decimal("250.00"),
            plaid_account_identifier="item-card",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.category, _ = Category.objects.get_or_create(
            owner=self.user, name="Groceries"
        )
        self.period = BudgetPeriod.objects.create(
            owner=self.user,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )

    def transaction(self, **overrides):
        values = {
            "plaid_transaction_id": f"txn-{Transaction.objects.count()}",
            "owner": self.user,
            "account": self.cash,
            "date": date(2026, 9, 10),
            "merchant_name": "Test merchant",
            "amount": Decimal("10.00"),
            "status": Transaction.Status.POSTED,
            "kind": Transaction.Kind.EXPENSE,
        }
        values.update(overrides)
        return Transaction.objects.create(**values)

    def test_posted_expenses_only_count_in_budget(self):
        self.transaction(amount=Decimal("25.00"))
        self.transaction(
            amount=Decimal("100.00"),
            kind=Transaction.Kind.INCOME,
            merchant_name="Employer",
        )
        self.transaction(
            amount=Decimal("50.00"),
            status=Transaction.Status.PENDING,
        )
        self.assertEqual(
            posted_expenses(self.user, self.period.start_date, self.period.end_date),
            Decimal("25.00"),
        )
        self.assertEqual(self.period.envelopes.count(), 0)

    def test_cash_and_pending_forecast_exclude_credit_card_account(self):
        self.transaction(
            amount=Decimal("40.00"),
            status=Transaction.Status.PENDING,
        )
        self.transaction(
            amount=Decimal("80.00"),
            account=self.card,
            status=Transaction.Status.PENDING,
        )
        self.assertEqual(pending_outflows(self.user), Decimal("40.00"))
        self.assertEqual(safe_cash(self.user), Decimal("960.00"))
        self.assertEqual(pending_forecast(self.user), Decimal("960.00"))

    def test_ready_to_assign_uses_posted_income_and_assignments(self):
        self.transaction(
            amount=Decimal("500.00"),
            kind=Transaction.Kind.INCOME,
            merchant_name="Paycheck",
        )
        envelope = Envelope.objects.create(
            owner=self.user,
            budget_period=self.period,
            category=self.category,
            assigned_amount=Decimal("200.00"),
        )
        self.assertEqual(self.period.ready_to_assign, Decimal("300.00"))
        self.assertEqual(envelope.spent_amount, Decimal("0.00"))

    def test_expected_paychecks_support_variable_pay(self):
        Paycheck.objects.create(
            owner=self.user,
            pay_date=date(2026, 9, 4),
            expected_amount=Decimal("1200.00"),
        )
        Paycheck.objects.create(
            owner=self.user,
            pay_date=date(2026, 9, 18),
            expected_amount=Decimal("1350.00"),
        )
        self.assertEqual(
            expected_income(self.user, date(2026, 9, 1), date(2026, 9, 30)),
            Decimal("2550.00"),
        )

    def test_budget_settings_require_surplus_percentages_to_total_one_hundred(self):
        settings = BudgetSettings(
            surplus_responsibilities_percent=60,
            surplus_savings_percent=30,
            surplus_discretionary_percent=5,
        )
        with self.assertRaises(ValidationError):
            settings.full_clean()

    def test_recurring_bill_due_day_is_validated(self):
        bill = RecurringBill(
            name="Rent",
            category=self.category,
            expected_amount=Decimal("900.00"),
            due_day=32,
        )
        with self.assertRaises(ValidationError):
            bill.full_clean()

    def test_received_paycheck_uses_received_amount(self):
        paycheck = Paycheck.objects.create(
            owner=self.user,
            pay_date=date(2026, 9, 4),
            expected_amount=Decimal("1200.00"),
            received_amount=Decimal("1150.00"),
            status=Paycheck.Status.RECEIVED,
        )
        self.assertEqual(paycheck.planned_amount, Decimal("1150.00"))

    def test_upcoming_bill_reserves_clamp_day_to_short_month(self):
        RecurringBill.objects.create(
            owner=self.user,
            name="Month-end bill",
            category=self.category,
            expected_amount=Decimal("75.00"),
            due_day=31,
        )
        self.assertEqual(
            upcoming_bill_reserves(self.user, date(2026, 2, 1), date(2026, 2, 28)),
            Decimal("75.00"),
        )

    def test_transfer_and_income_do_not_reduce_envelope(self):
        envelope = Envelope.objects.create(
            owner=self.user,
            budget_period=self.period,
            category=self.category,
            assigned_amount=Decimal("100.00"),
        )
        self.transaction(
            amount=Decimal("50.00"),
            kind=Transaction.Kind.TRANSFER,
            transfer_account=self.card,
        )
        self.transaction(
            amount=Decimal("25.00"),
            kind=Transaction.Kind.INCOME,
            merchant_name="Refund",
        )
        self.assertEqual(envelope.spent_amount, Decimal("0.00"))
        self.assertEqual(envelope.remaining_amount, Decimal("100.00"))


@override_settings(SECURE_SSL_REDIRECT=False)
class FinanceViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="test-user",
            password="strong-test-password",
        )
        self.client.login(
            username="test-user",
            password="strong-test-password",
        )
        self.account = Account.objects.create(
            owner=self.user,
            institution_name="Test Bank",
            name="Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("1000.00"),
            plaid_account_identifier="view-item",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.category = Category.objects.create(owner=self.user, name="View groceries")
        self.period = BudgetPeriod.objects.create(
            owner=self.user,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        self.envelope = Envelope.objects.create(
            owner=self.user,
            budget_period=self.period,
            category=self.category,
            assigned_amount=Decimal("300.00"),
        )

    def test_finance_pages_require_authentication(self):
        self.client.logout()
        for url_name in (
            "dashboard",
            "review-queue",
            "transactions",
            "budget",
            "planning",
            "rules",
            "accounts",
        ):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response.url)

    def test_dashboard_displays_safe_cash_and_ready_to_assign(self):
        Transaction.objects.create(
            owner=self.user,
            plaid_transaction_id="dashboard-pending",
            account=self.account,
            date=date(2026, 9, 10),
            merchant_name="Pending store",
            amount=Decimal("40.00"),
            status=Transaction.Status.PENDING,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Safe to spend")
        self.assertContains(response, "$960.00")
        self.assertContains(response, "Ready to assign")

    def test_budget_post_creates_auditable_allocation_event(self):
        response = self.client.post(
            reverse("budget"),
            {f"assigned_{self.envelope.pk}": "425.00"},
        )
        self.assertRedirects(response, reverse("budget"))
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.assigned_amount, Decimal("425.00"))
        allocation = BudgetAllocation.objects.get()
        self.assertEqual(allocation.amount, Decimal("125.00"))
        self.assertEqual(allocation.source, "manual")

    def test_budget_post_rejects_invalid_or_negative_assignments(self):
        for value in ("not-a-number", "-1.00"):
            response = self.client.post(
                reverse("budget"),
                {f"assigned_{self.envelope.pk}": value},
            )
            self.assertRedirects(response, reverse("budget"))
            self.envelope.refresh_from_db()
            self.assertEqual(self.envelope.assigned_amount, Decimal("300.00"))
        self.assertEqual(BudgetAllocation.objects.count(), 0)

    def test_review_queue_can_classify_transfer_without_category(self):
        transaction = Transaction.objects.create(
            owner=self.user,
            plaid_transaction_id="review-transfer",
            account=self.account,
            date=date(2026, 9, 10),
            merchant_name="Card payment",
            amount=Decimal("100.00"),
            status=Transaction.Status.POSTED,
        )
        response = self.client.post(
            reverse("review-queue"),
            {
                "transaction_ids": [transaction.pk],
                "kind": Transaction.Kind.TRANSFER,
                "category": "",
            },
        )
        self.assertRedirects(response, reverse("review-queue"))
        transaction.refresh_from_db()
        self.assertEqual(transaction.kind, Transaction.Kind.TRANSFER)
        self.assertIsNone(transaction.category)
        self.assertFalse(transaction.needs_review)

    def test_planning_page_lists_paychecks_and_bills(self):
        Paycheck.objects.create(
            owner=self.user,
            pay_date=date(2026, 9, 18),
            expected_amount=Decimal("1250.00"),
        )
        RecurringBill.objects.create(
            owner=self.user,
            name="Rent",
            category=self.category,
            expected_amount=Decimal("900.00"),
            due_day=1,
        )
        response = self.client.get(reverse("planning"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1250.00")
        self.assertContains(response, "Rent")

    def test_new_users_receive_private_finance_defaults(self):
        self.assertEqual(
            Category.objects.filter(owner=self.user).count(),
            13,
        )
        self.assertTrue(BudgetSettings.objects.filter(owner=self.user).exists())

    def test_finance_pages_do_not_expose_another_users_records(self):
        other_user = get_user_model().objects.create_user(
            username="other-user",
            password="test-password",
        )
        other_account = Account.objects.create(
            owner=other_user,
            institution_name="Other Bank",
            name="Other Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("9000.00"),
            plaid_account_identifier="other-item",
            plaid_access_token_encrypted=b"encrypted",
        )
        Transaction.objects.create(
            owner=other_user,
            plaid_transaction_id="other-transaction",
            account=other_account,
            date=date(2026, 9, 10),
            merchant_name="Private merchant",
            amount=Decimal("9000.00"),
            status=Transaction.Status.POSTED,
        )

        response = self.client.get(reverse("transactions"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private merchant")
        self.assertNotContains(response, "9000.00")

    def test_review_queue_cannot_update_another_users_transaction(self):
        other_user = get_user_model().objects.create_user(
            username="review-other-user",
            password="test-password",
        )
        other_account = Account.objects.create(
            owner=other_user,
            institution_name="Other Bank",
            name="Other Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("100.00"),
            plaid_account_identifier="review-other-item",
            plaid_access_token_encrypted=b"encrypted",
        )
        transaction = Transaction.objects.create(
            owner=other_user,
            plaid_transaction_id="review-other-transaction",
            account=other_account,
            date=date(2026, 9, 10),
            merchant_name="Other merchant",
            amount=Decimal("25.00"),
            status=Transaction.Status.POSTED,
        )

        response = self.client.post(
            reverse("review-queue"),
            {
                "transaction_ids": [transaction.pk],
                "kind": Transaction.Kind.TRANSFER,
                "category": "",
            },
        )

        self.assertRedirects(response, reverse("review-queue"))
        transaction.refresh_from_db()
        self.assertTrue(transaction.needs_review)


@override_settings(SECURE_SSL_REDIRECT=False)
class PlaidIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="plaid-user",
            password="test-password",
        )
        self.item = PlaidItem.objects.create(
            owner=self.user,
            item_id="item-1",
            institution_name="Sandbox Bank",
            access_token_encrypted=encrypt_access_token("access-sandbox"),
        )

    def test_access_tokens_round_trip_encrypted(self):
        encrypted = encrypt_access_token("secret-token")
        self.assertNotEqual(encrypted, b"secret-token")
        self.assertEqual(decrypt_access_token(encrypted), "secret-token")

    def test_sync_adds_accounts_and_transactions(self):
        class FakeClient:
            def get_accounts(self, access_token):
                return {
                    "accounts": [
                        {
                            "account_id": "account-1",
                            "name": "Checking",
                            "mask": "1234",
                            "type": "depository",
                            "subtype": "checking",
                            "balances": {"current": 500, "available": 450},
                        }
                    ]
                }

            def sync_transactions(self, access_token, cursor):
                return {
                    "added": [
                        {
                            "transaction_id": "plaid-txn-1",
                            "account_id": "account-1",
                            "date": "2026-09-17",
                            "name": "Market",
                            "merchant_name": "Market",
                            "amount": 42.50,
                            "pending": False,
                        },
                        {
                            "transaction_id": "plaid-income-1",
                            "account_id": "account-1",
                            "date": "2026-09-17",
                            "name": "Employer",
                            "amount": -1200,
                            "pending": False,
                        },
                    ],
                    "modified": [],
                    "removed": [],
                    "next_cursor": "cursor-1",
                    "has_more": False,
                }

        result = sync_item(self.item, FakeClient())
        self.assertNotIn("error", result)
        self.assertEqual(self.item.transactions_cursor, "cursor-1")
        self.assertEqual(self.item.status, PlaidItem.Status.CONNECTED)
        self.assertEqual(Account.objects.get(plaid_account_identifier="account-1").current_balance, Decimal("500.00"))
        self.assertEqual(
            Transaction.objects.get(plaid_transaction_id="plaid-income-1").kind,
            Transaction.Kind.INCOME,
        )

    def test_sync_soft_deletes_removed_transactions(self):
        account = Account.objects.create(
            owner=self.user,
            institution_name="Sandbox Bank",
            name="Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("500.00"),
            plaid_account_identifier="account-removed",
            plaid_item=self.item,
            plaid_access_token_encrypted=self.item.access_token_encrypted,
        )
        transaction = Transaction.objects.create(
            owner=self.user,
            plaid_transaction_id="removed-1",
            account=account,
            date=date(2026, 9, 1),
            merchant_name="Removed",
            amount=Decimal("10.00"),
            status=Transaction.Status.POSTED,
        )

        class FakeClient:
            def get_accounts(self, access_token):
                return {"accounts": []}

            def sync_transactions(self, access_token, cursor):
                return {
                    "added": [],
                    "modified": [],
                    "removed": [{"transaction_id": transaction.plaid_transaction_id}],
                    "next_cursor": "cursor-removed",
                    "has_more": False,
                }

        sync_item(self.item, FakeClient())
        transaction.refresh_from_db()
        self.assertTrue(transaction.is_removed)
        self.assertFalse(transaction.needs_review)

    def test_item_login_required_disables_future_sync(self):
        class FakeClient:
            def get_accounts(self, access_token):
                from .plaid import PlaidError

                raise PlaidError("Reconnect required", "ITEM_LOGIN_REQUIRED")

        result = sync_item(self.item, FakeClient())
        self.item.refresh_from_db()
        self.assertEqual(result["error_code"], "ITEM_LOGIN_REQUIRED")
        self.assertEqual(self.item.status, PlaidItem.Status.LOGIN_REQUIRED)

    @patch("finance.views.PlaidClient")
    @patch("finance.views.sync_accounts")
    def test_link_token_endpoint_returns_token(self, sync_mock, client_class):
        client_class.return_value.create_link_token.return_value = {
            "link_token": "link-sandbox-token"
        }
        user = get_user_model().objects.create_user(
            username="plaid-link-user",
            password="strong-test-password",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("plaid-link-token"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["link_token"], "link-sandbox-token")
