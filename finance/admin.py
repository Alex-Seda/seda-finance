from django.contrib import admin

from .models import Account, BudgetPeriod, Category, Envelope, Rule, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "name", "account_type", "current_balance", "last_synced_at")
    search_fields = ("institution_name", "name", "mask")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "merchant_name", "amount", "account", "category", "status", "needs_review")
    list_filter = ("status", "needs_review", "excluded_from_budget", "category")
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
