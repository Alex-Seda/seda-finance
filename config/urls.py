from django.contrib import admin
from django.urls import path

from finance import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("review/", views.review_queue, name="review-queue"),
    path("transactions/", views.transactions, name="transactions"),
    path("budget/", views.budget, name="budget"),
    path("rules/", views.rules, name="rules"),
    path("accounts/", views.accounts, name="accounts"),
    path("admin/", admin.site.urls),
]
