from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BudgetSettings, Category


STARTER_CATEGORIES = (
    "Housing",
    "Utilities",
    "Groceries",
    "Dining",
    "Transportation",
    "Healthcare",
    "Subscriptions",
    "Personal",
    "Savings",
    "Debt payments",
    "Investing",
    "Other",
)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def provision_finance_defaults(sender, instance, created, **kwargs):
    if not created:
        return
    Category.objects.bulk_create(
        [Category(owner=instance, name=name) for name in STARTER_CATEGORIES]
    )
    BudgetSettings.objects.create(owner=instance)
