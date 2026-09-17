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


def create_starter_categories(apps, schema_editor):
    Category = apps.get_model("finance", "Category")
    for name in STARTER_CATEGORIES:
        Category.objects.get_or_create(name=name)


def remove_starter_categories(apps, schema_editor):
    Category = apps.get_model("finance", "Category")
    Category.objects.filter(name__in=STARTER_CATEGORIES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0003_remove_budgetperiod_expected_income"),
    ]

    operations = [
        migrations.RunPython(create_starter_categories, remove_starter_categories),
    ]
