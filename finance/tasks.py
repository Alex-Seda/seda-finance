from celery import shared_task

from .models import PlaidItem
from .sync import sync_item


@shared_task
def sync_accounts(item_id=None):
    items = PlaidItem.objects.filter(pk=item_id) if item_id else PlaidItem.objects.all()
    return [sync_item(item) for item in items.exclude(status=PlaidItem.Status.LOGIN_REQUIRED)]
