from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum


class Account(models.Model):
    class AccountType(models.TextChoices):
        CHECKING = "checking", "Checking"
        SAVINGS = "savings", "Savings"
        CREDIT_CARD = "credit_card", "Credit card"

    institution_name = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    mask = models.CharField(max_length=4, blank=True)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2)
    available_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    plaid_item_id = models.CharField(max_length=255, unique=True)
    plaid_access_token_encrypted = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["institution_name", "name"]

    def __str__(self):
        suffix = f" (...{self.mask})" if self.mask else ""
        return f"{self.institution_name}: {self.name}{suffix}"

    @property
    def is_cash_account(self):
        return self.account_type in {
            self.AccountType.CHECKING,
            self.AccountType.SAVINGS,
        }


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_envelope = models.BooleanField(default=True)
    rollover_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"

    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        TRANSFER = "transfer", "Transfer"
        ADJUSTMENT = "adjustment", "Adjustment"

    plaid_transaction_id = models.CharField(max_length=255, unique=True)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    merchant_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices)
    kind = models.CharField(
        max_length=12,
        choices=Kind.choices,
        default=Kind.EXPENSE,
    )
    transfer_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_transfers",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    rule = models.ForeignKey(
        "Rule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_transactions",
    )
    notes = models.TextField(blank=True)
    excluded_from_budget = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["needs_review", "category"]),
            models.Index(fields=["kind", "status", "date"]),
        ]

    def __str__(self):
        return f"{self.date} - {self.merchant_name} ({self.amount})"


class BudgetPeriod(models.Model):
    start_date = models.DateField(unique=True)
    end_date = models.DateField()
    reset_day = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.start_date} to {self.end_date}"

    @property
    def posted_income(self):
        total = Transaction.objects.filter(
            date__gte=self.start_date,
            date__lte=self.end_date,
            status=Transaction.Status.POSTED,
            kind=Transaction.Kind.INCOME,
        ).aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def ready_to_assign(self):
        assigned = self.envelopes.aggregate(total=Sum("assigned_amount"))["total"]
        return self.posted_income + self.rollover_total - (assigned or Decimal("0.00"))

    @property
    def rollover_total(self):
        total = self.envelopes.aggregate(total=Sum("rollover_amount"))["total"]
        return total or Decimal("0.00")


class Envelope(models.Model):
    budget_period = models.ForeignKey(
        BudgetPeriod, on_delete=models.CASCADE, related_name="envelopes"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="envelopes"
    )
    assigned_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    rollover_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["budget_period", "category"],
                name="unique_envelope_per_period_category",
            )
        ]

    @property
    def spent_amount(self):
        total = self.category.transactions.filter(
            date__gte=self.budget_period.start_date,
            date__lte=self.budget_period.end_date,
            excluded_from_budget=False,
            status=Transaction.Status.POSTED,
            kind=Transaction.Kind.EXPENSE,
        ).aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def remaining_amount(self):
        return self.assigned_amount + self.rollover_amount - self.spent_amount

    @property
    def is_overspent(self):
        return self.remaining_amount < 0

    def __str__(self):
        return f"{self.budget_period}: {self.category}"


class Rule(models.Model):
    class MerchantMatchType(models.TextChoices):
        CONTAINS = "contains", "Contains"
        EXACT = "exact", "Exact"

    class Behavior(models.TextChoices):
        SUGGEST_ONLY = "suggest_only", "Suggest only"
        AUTO_APPLY = "auto_apply", "Auto-apply"

    name = models.CharField(max_length=100)
    merchant_match_type = models.CharField(
        max_length=10,
        choices=MerchantMatchType.choices,
        default=MerchantMatchType.CONTAINS,
    )
    merchant_pattern = models.CharField(max_length=255)
    minimum_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    maximum_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rules",
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="rules"
    )
    behavior = models.CharField(
        max_length=20,
        choices=Behavior.choices,
        default=Behavior.SUGGEST_ONLY,
    )
    confirmation_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Paycheck(models.Model):
    """An expected paycheck used for planning before income is received."""

    class Status(models.TextChoices):
        EXPECTED = "expected", "Expected"
        RECEIVED = "received", "Received"

    pay_date = models.DateField()
    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    received_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.EXPECTED,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pay_date"]

    @property
    def planned_amount(self):
        return self.received_amount if self.status == self.Status.RECEIVED else self.expected_amount

    def __str__(self):
        return f"{self.pay_date}: ${self.planned_amount:.2f}"


class PaycheckAllocation(models.Model):
    paycheck = models.ForeignKey(
        Paycheck, on_delete=models.CASCADE, related_name="allocations"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="paycheck_allocations"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_reserve = models.BooleanField(
        default=False,
        help_text="Reserve money for a due-soon bill or essential obligation.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["paycheck", "category"],
                name="unique_paycheck_category_allocation",
            )
        ]

    def __str__(self):
        return f"{self.paycheck} -> {self.category}: ${self.amount:.2f}"


class RecurringBill(models.Model):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="recurring_bills"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_bills",
    )
    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    due_day = models.PositiveSmallIntegerField()
    is_essential = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["due_day", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(due_day__gte=1) & Q(due_day__lte=31),
                name="recurring_bill_due_day_valid",
            )
        ]

    def __str__(self):
        return f"{self.name} (${self.expected_amount:.2f})"


class BudgetAllocation(models.Model):
    """An auditable allocation event for a monthly envelope."""

    budget_period = models.ForeignKey(
        BudgetPeriod, on_delete=models.CASCADE, related_name="allocation_events"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="budget_allocations"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=30, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BudgetSettings(models.Model):
    """Single-user settings for conservative paycheck planning."""

    base_paycheck_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    surplus_responsibilities_percent = models.PositiveSmallIntegerField(default=50)
    surplus_savings_percent = models.PositiveSmallIntegerField(default=30)
    surplus_discretionary_percent = models.PositiveSmallIntegerField(default=20)
    savings_floor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError

        percentages = (
            self.surplus_responsibilities_percent
            + self.surplus_savings_percent
            + self.surplus_discretionary_percent
        )
        if percentages != 100:
            raise ValidationError("Surplus allocation percentages must total 100.")

    @classmethod
    def current(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings
