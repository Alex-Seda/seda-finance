from django.conf import settings
from django.db import migrations


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


def provision_existing_users(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split(".", 1))
    Category = apps.get_model("finance", "Category")
    BudgetSettings = apps.get_model("finance", "BudgetSettings")
    for user in User.objects.all():
        for name in STARTER_CATEGORIES:
            Category.objects.get_or_create(owner=user, name=name)
        BudgetSettings.objects.get_or_create(owner=user)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0007_alter_budgetperiod_start_date_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(provision_existing_users, migrations.RunPython.noop),
    ]
