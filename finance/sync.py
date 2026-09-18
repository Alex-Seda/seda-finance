from django.utils import timezone

from .models import Account, PlaidItem
from .plaid import PlaidClient, PlaidError, apply_transaction, decrypt_access_token


def sync_item(item, client=None):
    client = client or PlaidClient()
    item.status = PlaidItem.Status.SYNCING
    item.last_sync_started_at = timezone.now()
    item.last_sync_error = ""
    item.save(update_fields=["status", "last_sync_started_at", "last_sync_error", "updated_at"])
    try:
        access_token = decrypt_access_token(item.access_token_encrypted)
        account_response = client.get_accounts(access_token)
        for account_data in account_response.get("accounts", []):
            Account.objects.update_or_create(
                plaid_item=item,
                plaid_account_identifier=account_data["account_id"],
                defaults={
                    "institution_name": item.institution_name,
                    "name": account_data["name"],
                    "mask": account_data.get("mask") or "",
                    "account_type": (
                        "credit_card"
                        if account_data.get("type") == "credit"
                        else (
                            "savings"
                            if account_data.get("subtype") == "savings"
                            else "checking"
                        )
                    ),
                    "current_balance": account_data.get("balances", {}).get("current") or 0,
                    "available_balance": account_data.get("balances", {}).get("available"),
                    "plaid_access_token_encrypted": item.access_token_encrypted,
                },
            )
        while True:
            response = client.sync_transactions(
                access_token,
                item.transactions_cursor,
            )
            for transaction in response.get("added", []):
                apply_transaction(item, transaction)
            for transaction in response.get("modified", []):
                apply_transaction(item, transaction)
            removed_ids = [entry["transaction_id"] for entry in response.get("removed", [])]
            if removed_ids:
                from .models import Transaction

                Transaction.objects.filter(
                    plaid_transaction_id__in=removed_ids
                ).update(is_removed=True, needs_review=False)
            item.transactions_cursor = response.get("next_cursor", item.transactions_cursor)
            if not response.get("has_more"):
                break
        item.status = PlaidItem.Status.CONNECTED
        item.last_synced_at = timezone.now()
        item.save(update_fields=[
            "transactions_cursor",
            "status",
            "last_synced_at",
            "updated_at",
        ])
        return {"item_id": item.item_id, "added_or_updated": True}
    except PlaidError as exc:
        item.status = (
            PlaidItem.Status.LOGIN_REQUIRED
            if exc.error_code == "ITEM_LOGIN_REQUIRED"
            else PlaidItem.Status.ERROR
        )
        item.last_sync_error = str(exc)
        item.save(update_fields=["status", "last_sync_error", "updated_at"])
        return {"item_id": item.item_id, "error": str(exc), "error_code": exc.error_code}
