from django.contrib import admin

from .models import (
    Account,
    BudgetAllocation,
    BudgetPeriod,
    BudgetSettings,
    Category,
    Envelope,
    Paycheck,
    PaycheckAllocation,
    PlaidItem,
    RecurringBill,
    Rule,
    Transaction,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "name", "account_type", "current_balance", "last_synced_at")
    search_fields = ("institution_name", "name", "mask")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "merchant_name",
        "amount",
        "account",
        "category",
        "kind",
        "status",
        "needs_review",
    )
    list_filter = ("status", "kind", "needs_review", "excluded_from_budget", "category")
    search_fields = ("merchant_name", "plaid_transaction_id", "notes")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_envelope", "rollover_enabled", "is_active")
    list_filter = ("is_envelope", "rollover_enabled", "is_active")


@admin.register(BudgetPeriod)
class BudgetPeriodAdmin(admin.ModelAdmin):
    list_display = ("start_date", "end_date", "reset_day")


@admin.register(Envelope)
class EnvelopeAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "category", "assigned_amount", "rollover_amount")


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "behavior", "confirmation_count", "is_active")
    list_filter = ("behavior", "is_active", "merchant_match_type")
    search_fields = ("name", "merchant_pattern")


@admin.register(Paycheck)
class PaycheckAdmin(admin.ModelAdmin):
    list_display = ("pay_date", "expected_amount", "received_amount", "status")
    list_filter = ("status",)


@admin.register(PaycheckAllocation)
class PaycheckAllocationAdmin(admin.ModelAdmin):
    list_display = ("paycheck", "category", "amount", "is_reserve")
    list_filter = ("is_reserve", "category")


@admin.register(RecurringBill)
class RecurringBillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "expected_amount", "due_day", "is_essential", "is_active")
    list_filter = ("is_essential", "is_active", "category")


@admin.register(BudgetAllocation)
class BudgetAllocationAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "category", "amount", "source", "created_at")
    list_filter = ("source", "category")


@admin.register(BudgetSettings)
class BudgetSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "base_paycheck_amount",
        "surplus_responsibilities_percent",
        "surplus_savings_percent",
        "surplus_discretionary_percent",
        "savings_floor",
    )

    def has_add_permission(self, request):
        return not BudgetSettings.objects.exists()


@admin.register(PlaidItem)
class PlaidItemAdmin(admin.ModelAdmin):
    list_display = (
        "item_id",
        "institution_name",
        "status",
        "last_synced_at",
        "last_sync_error",
    )
    list_filter = ("status",)
    search_fields = ("item_id", "institution_name")
    readonly_fields = ("access_token_encrypted",)
