from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum


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

    plaid_transaction_id = models.CharField(max_length=255, unique=True)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    merchant_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices)
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
