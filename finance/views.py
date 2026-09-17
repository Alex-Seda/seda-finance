from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Account, BudgetPeriod, Category, Envelope, Rule, Transaction


def dashboard(request):
    recent_transactions = Transaction.objects.select_related("account", "category")[:8]
    review_count = Transaction.objects.filter(needs_review=True).count()
    account_balance = Account.objects.aggregate(total=Sum("current_balance"))["total"] or Decimal("0")
    current_period = BudgetPeriod.objects.first()
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
        "current_period": current_period,
        "envelopes": envelopes,
    })


@require_http_methods(["GET", "POST"])
def review_queue(request):
    categories = Category.objects.filter(is_active=True)
    if request.method == "POST":
        transaction_ids = request.POST.getlist("transaction_ids")
        category_id = request.POST.get("category")
        category = get_object_or_404(categories, pk=category_id)
        Transaction.objects.filter(pk__in=transaction_ids).update(
            category=category, needs_review=False
        )
        messages.success(request, f"{len(transaction_ids)} transaction(s) categorized.")
        return redirect("review-queue")
    transactions = Transaction.objects.filter(needs_review=True).select_related("account", "category")
    return render(request, "finance/review_queue.html", {
        "transactions": transactions,
        "categories": categories,
    })


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
def budget(request):
    period = BudgetPeriod.objects.first()
    if request.method == "POST":
        if not period:
            messages.error(request, "Create a budget period before assigning envelope amounts.")
            return redirect("budget")
        for envelope in period.envelopes.all():
            value = request.POST.get(f"assigned_{envelope.pk}")
            if value is not None:
                envelope.assigned_amount = value or Decimal("0")
                envelope.save(update_fields=["assigned_amount"])
        messages.success(request, "Budget assignments updated.")
        return redirect("budget")
    envelopes = period.envelopes.select_related("category") if period else []
    return render(request, "finance/budget.html", {"period": period, "envelopes": envelopes})


@require_http_methods(["GET", "POST"])
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


def accounts(request):
    return render(request, "finance/accounts.html", {"accounts": Account.objects.all()})
