from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from finance import views


urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("review/", views.review_queue, name="review-queue"),
    path("transactions/", views.transactions, name="transactions"),
    path("budget/", views.budget, name="budget"),
    path("planning/", views.planning, name="planning"),
    path("rules/", views.rules, name="rules"),
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/plaid/link-token/", views.plaid_link_token, name="plaid-link-token"),
    path("accounts/plaid/exchange/", views.plaid_exchange_token, name="plaid-exchange-token"),
    path(
        "accounts/plaid/<int:item_id>/sync/",
        views.plaid_sync_now,
        name="plaid-sync-now",
    ),
    path("admin/", admin.site.urls),
]
