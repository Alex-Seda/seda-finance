import base64
import hashlib
import os
from datetime import datetime, timezone
from decimal import Decimal

import requests
from cryptography.fernet import Fernet
from django.conf import settings

from .models import Account, PlaidItem, Transaction


class PlaidError(Exception):
    def __init__(self, message, error_code=""):
        super().__init__(message)
        self.error_code = error_code


def _fernet():
    configured_key = os.getenv("PLAID_TOKEN_ENCRYPTION_KEY")
    source = configured_key or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode()).digest())
    return Fernet(key)


def encrypt_access_token(token):
    return _fernet().encrypt(token.encode("utf-8"))


def decrypt_access_token(value):
    return _fernet().decrypt(bytes(value)).decode("utf-8")


class PlaidClient:
    endpoints = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.base_url = self.endpoints.get(settings.PLAID_ENV, self.endpoints["sandbox"])

    def _post(self, path, payload):
        if not settings.PLAID_CLIENT_ID or not settings.PLAID_SECRET:
            raise PlaidError("Plaid credentials are not configured.")
        response = self.session.post(
            f"{self.base_url}{path}",
            json={
                "client_id": settings.PLAID_CLIENT_ID,
                "secret": settings.PLAID_SECRET,
                **payload,
            },
            timeout=30,
        )
        data = response.json()
        if response.status_code >= 400 or data.get("error_code"):
            raise PlaidError(
                data.get("error_message", "Plaid request failed."),
                data.get("error_code", ""),
            )
        return data

    def create_link_token(self, user_id):
        return self._post(
            "/link/token/create",
            {
                "user": {"client_user_id": str(user_id)},
                "client_name": "Seda Finance",
                "products": ["transactions"],
                "transactions": {"days_requested": 90},
                "country_codes": ["US"],
                "language": "en",
            },
        )

    def exchange_public_token(self, public_token):
        return self._post("/item/public_token/exchange", {"public_token": public_token})

    def get_item(self, access_token):
        return self._post("/item/get", {"access_token": access_token})

    def get_accounts(self, access_token):
        return self._post("/accounts/balance/get", {"access_token": access_token})

    def sync_transactions(self, access_token, cursor=""):
        return self._post(
            "/transactions/sync",
            {"access_token": access_token, "cursor": cursor} if cursor else {"access_token": access_token},
        )


def plaid_account_type(plaid_type, subtype):
    if subtype == "credit card" or plaid_type == "credit":
        return Account.AccountType.CREDIT_CARD
    if subtype == "savings":
        return Account.AccountType.SAVINGS
    return Account.AccountType.CHECKING


def parse_plaid_date(value):
    return datetime.fromisoformat(value).date()


def apply_transaction(item, payload):
    account = Account.objects.get(
        plaid_item=item,
        plaid_account_identifier=payload["account_id"],
    )
    raw_amount = Decimal(str(payload["amount"]))
    existing = Transaction.objects.filter(
        plaid_transaction_id=payload["transaction_id"]
    ).first()
    transaction, created = Transaction.objects.update_or_create(
        plaid_transaction_id=payload["transaction_id"],
        defaults={
            "account": account,
            "date": parse_plaid_date(payload["date"]),
            "merchant_name": payload.get("merchant_name") or payload.get("name") or "Unknown",
            "amount": abs(raw_amount),
            "status": (
                Transaction.Status.PENDING
                if payload.get("pending")
                else Transaction.Status.POSTED
            ),
            "kind": (
                existing.kind
                if existing
                else (
                    Transaction.Kind.INCOME
                    if raw_amount < 0
                    else Transaction.Kind.EXPENSE
                )
            ),
            "is_removed": False,
            "plaid_modified_at": datetime.now(timezone.utc),
        },
    )
    return transaction
