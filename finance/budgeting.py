from decimal import Decimal
from calendar import monthrange

from django.db.models import Sum

from .models import Account, BudgetPeriod, Paycheck, RecurringBill, Transaction

ZERO = Decimal("0.00")


def posted_income(start_date, end_date):
    return (
        Transaction.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            status=Transaction.Status.POSTED,
            kind=Transaction.Kind.INCOME,
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )


def posted_expenses(start_date, end_date):
    return (
        Transaction.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            status=Transaction.Status.POSTED,
            kind=Transaction.Kind.EXPENSE,
            excluded_from_budget=False,
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )


def pending_outflows():
    return (
        Transaction.objects.filter(
            status=Transaction.Status.PENDING,
            kind=Transaction.Kind.EXPENSE,
            account__account_type__in=[
                Account.AccountType.CHECKING,
                Account.AccountType.SAVINGS,
            ],
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )


def cash_balance():
    return (
        Account.objects.filter(
            account_type__in=[
                Account.AccountType.CHECKING,
                Account.AccountType.SAVINGS,
            ]
        ).aggregate(total=Sum("current_balance"))["total"]
        or ZERO
    )


def safe_cash():
    """Cash currently held in cash accounts after pending expense outflows."""
    return cash_balance() - pending_outflows()


def pending_forecast():
    """Net pending effect for display only; posted totals remain authoritative."""
    pending_income = (
        Transaction.objects.filter(
            status=Transaction.Status.PENDING,
            kind=Transaction.Kind.INCOME,
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    return safe_cash() + pending_income


def expected_income(start_date, end_date):
    return sum(
        (
            paycheck.planned_amount
            for paycheck in Paycheck.objects.filter(
                pay_date__gte=start_date,
                pay_date__lte=end_date,
            )
        ),
        ZERO,
    )


def upcoming_bill_reserves(start_date, end_date):
    return sum(
        (
            bill.expected_amount
            for bill in RecurringBill.objects.filter(is_active=True)
            if start_date
            <= start_date.replace(
                day=min(bill.due_day, monthrange(start_date.year, start_date.month)[1])
            )
            <= end_date
        ),
        ZERO,
    )


def ready_to_assign(period: BudgetPeriod):
    assigned = period.envelopes.aggregate(total=Sum("assigned_amount"))["total"] or ZERO
    return posted_income(period.start_date, period.end_date) + period.rollover_total - assigned


def paycheck_safe_to_spend(paycheck: Paycheck, next_pay_date=None):
    """Return the amount left after explicit paycheck allocations and reserves."""
    allocated = paycheck.allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    return paycheck.planned_amount - allocated


def safe_to_spend_by_envelope(period: BudgetPeriod):
    """Return current posted envelope balances for the paycheck planning view."""
    return {
        envelope.category_id: envelope.remaining_amount
        for envelope in period.envelopes.select_related("category")
    }
