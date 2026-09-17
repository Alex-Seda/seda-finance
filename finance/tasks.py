from celery import shared_task


@shared_task
def sync_accounts():
    """Placeholder for scheduled Plaid synchronization."""
    return "Plaid synchronization is not configured yet."
