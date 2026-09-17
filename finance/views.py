from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .budgeting import (
    cash_balance,
    expected_income,
    pending_forecast,
    pending_outflows,
    ready_to_assign,
    safe_cash,
)
from .models import (
    Account,
    BudgetAllocation,
    BudgetPeriod,
    Category,
    Envelope,
    Paycheck,
    RecurringBill,
    Rule,
    Transaction,
)


@login_required
def dashboard(request):
    recent_transactions = Transaction.objects.select_related("account", "category")[:8]
    review_count = Transaction.objects.filter(needs_review=True).count()
    current_period = BudgetPeriod.objects.first()
    account_balance = cash_balance()
    safe_to_spend = safe_cash()
    forecast_cash = pending_forecast()
    envelopes = (
        Envelope.objects.select_related("category", "budget_period")
        .filter(budget_period=current_period)
        if current_period
        else []
    )
    return render(request, "finance/dashboard.html", {
        "recent_transactions": recent_transactions,
        "review_count": review_count,
        "account_balance": account_balance,
        "safe_cash": safe_to_spend,
        "forecast_cash": forecast_cash,
        "pending_outflows": pending_outflows(),
        "current_period": current_period,
        "ready_to_assign": ready_to_assign(current_period) if current_period else Decimal("0"),
        "expected_income": (
            expected_income(current_period.start_date, current_period.end_date)
            if current_period
            else Decimal("0")
        ),
        "envelopes": envelopes,
    })


@require_http_methods(["GET", "POST"])
@login_required
def review_queue(request):
    categories = Category.objects.filter(is_active=True)
    if request.method == "POST":
        transaction_ids = request.POST.getlist("transaction_ids")
        category_id = request.POST.get("category")
        kind = request.POST.get("kind", Transaction.Kind.EXPENSE)
        category = get_object_or_404(categories, pk=category_id) if category_id else None
        if kind == Transaction.Kind.EXPENSE and category is None:
            messages.error(request, "Choose a category for expense transactions.")
            return redirect("review-queue")
        Transaction.objects.filter(pk__in=transaction_ids).update(
            category=category if kind == Transaction.Kind.EXPENSE else None,
            kind=kind,
            needs_review=False,
        )
        messages.success(request, f"{len(transaction_ids)} transaction(s) categorized.")
        return redirect("review-queue")
    transactions = Transaction.objects.filter(needs_review=True).select_related("account", "category")
    return render(request, "finance/review_queue.html", {
        "transactions": transactions,
        "categories": categories,
    })


@login_required
def transactions(request):
    query = request.GET.get("q", "").strip()
    transaction_list = Transaction.objects.select_related("account", "category")
    if query:
        transaction_list = transaction_list.filter(
            Q(merchant_name__icontains=query)
            | Q(notes__icontains=query)
            | Q(account__name__icontains=query)
        )
    return render(request, "finance/transactions.html", {
        "transactions": transaction_list,
        "query": query,
    })


@require_http_methods(["GET", "POST"])
@login_required
def budget(request):
    period = BudgetPeriod.objects.first()
    if request.method == "POST":
        if not period:
            messages.error(request, "Create a budget period before assigning envelope amounts.")
            return redirect("budget")
        for envelope in period.envelopes.all():
            value = request.POST.get(f"assigned_{envelope.pk}")
            if value is not None:
                try:
                    assigned_amount = Decimal(value or "0")
                except InvalidOperation:
                    messages.error(
                        request,
                        f"Enter a valid amount for {envelope.category.name}.",
                    )
                    return redirect("budget")
                if assigned_amount < 0:
                    messages.error(
                        request,
                        f"Assigned amount for {envelope.category.name} cannot be negative.",
                    )
                    return redirect("budget")
                previous_amount = envelope.assigned_amount
                envelope.assigned_amount = assigned_amount
                envelope.save(update_fields=["assigned_amount"])
                difference = envelope.assigned_amount - previous_amount
                if difference:
                    BudgetAllocation.objects.create(
                        budget_period=period,
                        category=envelope.category,
                        amount=difference,
                        source="manual",
                    )
        messages.success(request, "Budget assignments updated.")
        return redirect("budget")
    envelopes = period.envelopes.select_related("category") if period else []
    return render(
        request,
        "finance/budget.html",
        {
            "period": period,
            "envelopes": envelopes,
            "expected_income": (
                expected_income(period.start_date, period.end_date)
                if period
                else Decimal("0")
            ),
            "envelopes": (
                period.envelopes.select_related("category")
                if period
                else []
            ),
        },
    )


@require_http_methods(["GET", "POST"])
@login_required
def rules(request):
    categories = Category.objects.filter(is_active=True)
    accounts = Account.objects.all()
    if request.method == "POST":
        category = get_object_or_404(categories, pk=request.POST.get("category"))
        Rule.objects.create(
            name=request.POST["name"],
            merchant_pattern=request.POST["merchant_pattern"],
            merchant_match_type=request.POST.get("merchant_match_type", Rule.MerchantMatchType.CONTAINS),
            behavior=request.POST.get("behavior", Rule.Behavior.SUGGEST_ONLY),
            category=category,
            account=Account.objects.filter(pk=request.POST.get("account")).first()
            if request.POST.get("account") else None,
        )
        messages.success(request, "Rule created.")
        return redirect("rules")
    return render(request, "finance/rules.html", {
        "rules": Rule.objects.select_related("category", "account"),
        "categories": categories,
        "accounts": accounts,
    })


@login_required
def accounts(request):
    return render(request, "finance/accounts.html", {"accounts": Account.objects.all()})


@login_required
def planning(request):
    period = BudgetPeriod.objects.first()
    paychecks = Paycheck.objects.all()[:8]
    bills = RecurringBill.objects.filter(is_active=True)
    return render(
        request,
        "finance/planning.html",
        {
            "period": period,
            "paychecks": paychecks,
            "bills": bills,
            "expected_income": (
                expected_income(period.start_date, period.end_date)
                if period
                else Decimal("0")
            ),
        },
    )
