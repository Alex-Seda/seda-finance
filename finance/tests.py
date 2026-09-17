from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
)


class BudgetingTests(TestCase):
    def setUp(self):
        self.cash = Account.objects.create(
            institution_name="Test Bank",
            name="Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("1000.00"),
            plaid_item_id="item-checking",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.card = Account.objects.create(
            institution_name="Test Bank",
            name="Card",
            account_type=Account.AccountType.CREDIT_CARD,
            current_balance=Decimal("250.00"),
            plaid_item_id="item-card",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.category, _ = Category.objects.get_or_create(name="Groceries")
        self.period = BudgetPeriod.objects.create(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )

    def transaction(self, **overrides):
        values = {
            "plaid_transaction_id": f"txn-{Transaction.objects.count()}",
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
            posted_expenses(self.period.start_date, self.period.end_date),
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
        self.assertEqual(pending_outflows(), Decimal("40.00"))
        self.assertEqual(safe_cash(), Decimal("960.00"))
        self.assertEqual(pending_forecast(), Decimal("960.00"))

    def test_ready_to_assign_uses_posted_income_and_assignments(self):
        self.transaction(
            amount=Decimal("500.00"),
            kind=Transaction.Kind.INCOME,
            merchant_name="Paycheck",
        )
        envelope = Envelope.objects.create(
            budget_period=self.period,
            category=self.category,
            assigned_amount=Decimal("200.00"),
        )
        self.assertEqual(self.period.ready_to_assign, Decimal("300.00"))
        self.assertEqual(envelope.spent_amount, Decimal("0.00"))

    def test_expected_paychecks_support_variable_pay(self):
        Paycheck.objects.create(
            pay_date=date(2026, 9, 4),
            expected_amount=Decimal("1200.00"),
        )
        Paycheck.objects.create(
            pay_date=date(2026, 9, 18),
            expected_amount=Decimal("1350.00"),
        )
        self.assertEqual(
            expected_income(date(2026, 9, 1), date(2026, 9, 30)),
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
            pay_date=date(2026, 9, 4),
            expected_amount=Decimal("1200.00"),
            received_amount=Decimal("1150.00"),
            status=Paycheck.Status.RECEIVED,
        )
        self.assertEqual(paycheck.planned_amount, Decimal("1150.00"))

    def test_upcoming_bill_reserves_clamp_day_to_short_month(self):
        RecurringBill.objects.create(
            name="Month-end bill",
            category=self.category,
            expected_amount=Decimal("75.00"),
            due_day=31,
        )
        self.assertEqual(
            upcoming_bill_reserves(date(2026, 2, 1), date(2026, 2, 28)),
            Decimal("75.00"),
        )

    def test_transfer_and_income_do_not_reduce_envelope(self):
        envelope = Envelope.objects.create(
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
            institution_name="Test Bank",
            name="Checking",
            account_type=Account.AccountType.CHECKING,
            current_balance=Decimal("1000.00"),
            plaid_item_id="view-item",
            plaid_access_token_encrypted=b"encrypted",
        )
        self.category = Category.objects.create(name="View groceries")
        self.period = BudgetPeriod.objects.create(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        self.envelope = Envelope.objects.create(
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
            pay_date=date(2026, 9, 18),
            expected_amount=Decimal("1250.00"),
        )
        RecurringBill.objects.create(
            name="Rent",
            category=self.category,
            expected_amount=Decimal("900.00"),
            due_day=1,
        )
        response = self.client.get(reverse("planning"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1250.00")
        self.assertContains(response, "Rent")
