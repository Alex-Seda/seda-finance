import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0004_seed_starter_categories"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlaidItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_id", models.CharField(max_length=255, unique=True)),
                ("institution_name", models.CharField(blank=True, max_length=255)),
                ("access_token_encrypted", models.BinaryField()),
                ("transactions_cursor", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("connected", "Connected"), ("syncing", "Syncing"), ("login_required", "Reconnect required"), ("error", "Sync error")], default="connected", max_length=20)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_error", models.TextField(blank=True)),
                ("sync_requested_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["institution_name", "item_id"]},
        ),
        migrations.RenameField(
            model_name="account",
            old_name="plaid_item_id",
            new_name="plaid_account_identifier",
        ),
        migrations.AddField(
            model_name="account",
            name="plaid_item",
            field=models.ForeignKey(
                blank=True,
                db_column="plaid_item_fk_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accounts",
                to="finance.plaiditem",
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="is_removed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="transaction",
            name="plaid_modified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["is_removed", "date"], name="finance_tra_is_remo_66850d_idx"),
        ),
        migrations.AlterField(
            model_name="account",
            name="plaid_account_identifier",
            field=models.CharField(
                db_column="plaid_item_id",
                max_length=255,
                unique=True,
            ),
        ),
    ]
