# Seda Finance Developer Outline

This document is the fastest way to understand the repository and make a safe
change. It describes the current implementation, not the entire future product
specification. Some models and settings exist ahead of their complete UI
workflows.

## 1. Product and current scope

Seda Finance is a self-hosted Django personal-finance application for:

- Connecting checking, savings, and credit-card accounts through Plaid.
- Importing account balances and transactions.
- Classifying transactions as expenses, income, or transfers.
- Managing calendar-month envelope budgets.
- Planning around biweekly paychecks and recurring bills.
- Showing cash and safe-to-spend estimates.

The application now supports multiple users at the data model and view-query
layers. Every financial record has an owner and authenticated finance views
scope reads and writes to the current user. Plaid support is implemented for
Sandbox and is not yet production-ready. Two-factor authentication, automatic
rule processing during sync, and complete in-app onboarding are still pending.

## 2. Repository map

```text
config/
  settings.py       Django settings, database, security, Celery schedule
  urls.py           URL-to-view routing
  celery.py         Celery application initialization
  wsgi.py           WSGI entrypoint

finance/
  models.py         Database schema and model-level calculations
  views.py          Authenticated HTML views and JSON endpoints
  budgeting.py      Query-based financial calculations
  plaid.py          Plaid HTTP client and token encryption
  sync.py           Account and transaction synchronization
  tasks.py          Celery task entrypoints
  admin.py          Django admin configuration
  tests.py          Django tests
  migrations/       Versioned database schema changes
  static/           Application CSS and JavaScript

templates/
  base.html         Shared application shell and navigation
  finance/          Application page templates
  registration/     Login template
  admin/            Admin theme customization

compose.yaml        Web, PostgreSQL, Redis, worker, and beat services
Dockerfile          Python application image
manage.py           Django management entrypoint
requirements.txt    Python dependencies
.env.example        Environment variable template
README.md           Project setup and status summary
developer-outline.md This document
user-guide.md       End-user setup and operating guide
```

## 3. Request and processing architecture

### Browser request

```text
Browser
  -> config/urls.py
  -> finance/views.py
  -> finance/models.py or finance/budgeting.py
  -> templates/finance/*.html
  -> HTML response
```

All finance pages currently use Django's `login_required` decorator. Form
submissions use normal Django POST requests with CSRF tokens. Plaid connection
and manual sync use JSON endpoints called by browser JavaScript.

### Background Plaid sync

```text
Celery Beat every 6 hours
  -> finance.tasks.sync_accounts
  -> finance.sync.sync_item
  -> finance.plaid.PlaidClient
  -> Plaid API
  -> Account / PlaidItem / Transaction rows
```

The Accounts page can also enqueue the same task for one Plaid item.

## 4. Application startup and environments

### Local Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Local development can use SQLite when `DATABASE_URL` is absent. Keep
`DJANGO_FORCE_HTTPS` unset or set it to `False` for plain HTTP local
development. Set `DJANGO_FORCE_HTTPS=True` only when Django is behind an HTTPS
reverse proxy.

### Docker Compose

```bash
cp .env.example .env
# Replace all generate-* values.
docker compose up --build
```

Compose runs:

- `web`: Gunicorn plus migrations and static-file collection.
- `db`: PostgreSQL.
- `redis`: Password-protected Redis.
- `worker`: Celery worker.
- `beat`: Celery scheduler.

PostgreSQL and Redis are internal Compose services and are not published on
host ports. The web service is bound to `127.0.0.1:8000` for local use. A real
deployment should put Gunicorn behind an HTTPS reverse proxy.

### Important settings

| Setting | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django signing key; must be unique and secret |
| `DJANGO_DEBUG` | Defaults to `False`; use `True` only for local development |
| `DJANGO_FORCE_HTTPS` | Enables HTTPS redirects, secure cookies, and HSTS |
| `DJANGO_ALLOWED_HOSTS` | Hostnames accepted by Django |
| `DATABASE_URL` | Optional PostgreSQL connection URL |
| `POSTGRES_*` | Compose database configuration |
| `REDIS_PASSWORD` | Compose Redis authentication |
| `CELERY_BROKER_URL` | Celery broker |
| `CELERY_RESULT_BACKEND` | Celery result backend |
| `PLAID_CLIENT_ID` | Plaid API client ID |
| `PLAID_SECRET` | Plaid API secret |
| `PLAID_ENV` | `sandbox`, `development`, or `production` |
| `PLAID_TOKEN_ENCRYPTION_KEY` | Dedicated Plaid token key; required when `DJANGO_DEBUG=False` |

The Plaid encryption helper derives a Fernet key only from
`PLAID_TOKEN_ENCRYPTION_KEY`. Production fails closed when either the Django
signing secret or the dedicated Plaid key is absent. Debug-mode local
development may generate ephemeral secrets, which means encrypted local Plaid
tokens are not expected to survive a process restart unless explicit keys are
configured.

## 5. URL and view reference

Routes are declared in `config/urls.py` and implemented in
`finance/views.py`.

| Route | View | Behavior |
|---|---|---|
| `/` | `dashboard` | Loads current period, cash, forecasts, review count, and envelopes |
| `/review/` | `review_queue` | Lists pending review rows and bulk-classifies them |
| `/transactions/` | `transactions` | Searches merchant, notes, and account name |
| `/budget/` | `budget` | Displays and updates envelope assignments |
| `/planning/` | `planning` | Displays paychecks, bills, and envelope balances |
| `/rules/` | `rules` | Creates and lists categorization rules |
| `/accounts/` | `accounts` | Displays Plaid items and local accounts |
| `/accounts/plaid/link-token/` | `plaid_link_token` | Returns a Plaid Link token |
| `/accounts/plaid/exchange/` | `plaid_exchange_token` | Stores a connected Plaid item and queues sync |
| `/accounts/plaid/<id>/sync/` | `plaid_sync_now` | Queues a manual sync |
| `/admin/` | Django admin | Administrative CRUD for all current models |

When changing a view:

1. Find its route in `config/urls.py`.
2. Read the view in `finance/views.py`.
3. Read the template named by the view.
4. Follow model properties or helpers called by the view.
5. Add or update a test in `finance/tests.py`.

## 6. Model reference

All models are in `finance/models.py`.

### `Account`

Represents a checking, savings, or credit-card account. Plaid-imported accounts
link to `PlaidItem` and retain current and available balances.

`is_cash_account` is true only for checking and savings accounts. Budget cash
calculations use this distinction to exclude credit-card balances from positive
cash.

### `Category`

Represents a user-defined category. Categories can participate in envelopes and
can be configured for rollover.

Migration `0004_seed_starter_categories.py` creates the initial categories:
Housing, Utilities, Groceries, Dining, Transportation, Healthcare,
Subscriptions, Personal, Savings, Debt payments, Investing, and Other.

### `Transaction`

Represents an imported or manually created transaction.

Important fields:

- `plaid_transaction_id`: deduplication key.
- `status`: `pending` or `posted`.
- `kind`: `expense`, `income`, `transfer`, or `adjustment`.
- `category`: nullable until categorized.
- `needs_review`: drives the review queue.
- `excluded_from_budget`: excludes posted expense from envelope spending.
- `is_removed`: soft-delete marker for Plaid removals.
- `transfer_account`: optional transfer counterpart.

Plaid positive amounts become expenses and negative amounts become income. The
application stores amounts as positive `Decimal` values and uses `kind` to
represent direction.

### `BudgetPeriod`

Represents a calendar-month budget range. It calculates:

- `posted_income`: posted income transactions in the period.
- `rollover_total`: sum of envelope rollover amounts.
- `ready_to_assign`: posted income plus rollover minus assignments.

The current views select the newest period with `BudgetPeriod.objects.first()`.

### `Envelope`

Connects one category to one budget period. It stores assigned and rollover
amounts and calculates:

```text
remaining = assigned + rollover - posted expense spending
```

Overspending is displayed but does not block transactions.

### `Rule`

Stores merchant matching rules with contains/exact matching, optional amount
ranges, optional account scope, and suggest-only/auto-apply behavior. Rule
creation exists, but automatic rule processing during Plaid sync is not yet
implemented.

### `Paycheck`

Stores expected or received paychecks. `planned_amount` uses
`received_amount` when the paycheck is marked received; otherwise it uses
`expected_amount`.

### `PaycheckAllocation`

Stores the amount of a paycheck assigned to a category. `is_reserve` marks an
allocation intended for bills or essential obligations.

### `RecurringBill`

Stores a recurring bill, category, expected amount, due day, account, and
essential/active flags. Due days are constrained to 1–31.

### `BudgetAllocation`

Stores an audit event whenever a budget view changes an envelope assignment.
The stored amount is the difference from the previous assignment.

### `BudgetSettings`

Stores the manual base paycheck, surplus percentages, and savings floor. The
three surplus percentages must total 100. The storage model exists; automatic
surplus and shortfall recommendations are not complete.

### `PlaidItem`

Represents one connected Plaid institution/item. It stores the encrypted access
token, transactions cursor, sync status, timestamps, and last error.

Statuses:

- `connected`
- `syncing`
- `login_required`
- `error`

## 7. Financial calculations

Calculation helpers are in `finance/budgeting.py`.

### Cash

```text
cash_balance =
  checking current balances
  + savings current balances
```

```text
safe_cash =
  cash_balance
  - pending expense transactions in checking/savings
```

```text
pending_forecast =
  safe_cash
  + pending income
```

Credit-card balances and pending credit-card expenses are not included in
positive cash possession.

### Budget spending

Only posted, non-excluded expenses count toward envelope spending. Pending
transactions are display/forecast data and are not official budget spending.

### Expected income

Expected income is the sum of paycheck `planned_amount` values in the period.
It is displayed for planning, but only posted income contributes to Ready to
Assign.

### Paycheck safe-to-spend

The current helper calculates planned paycheck amount minus explicit paycheck
allocations. Full due-date-aware paycheck recommendations are still future
work.

## 8. Plaid integration

Plaid code is intentionally split into provider and synchronization layers.

### `finance/plaid.py`

Contains:

- `PlaidError`: carries Plaid error code.
- `_fernet()`: builds the Fernet cipher.
- `encrypt_access_token()` and `decrypt_access_token()`.
- `PlaidClient`: HTTP calls to Plaid.
- `parse_plaid_date()`.
- `apply_transaction()`: converts a Plaid transaction into a local row.

`PlaidClient` supports:

- Link token creation.
- Public token exchange.
- Item retrieval.
- Account balance retrieval.
- Cursor-based transaction sync.

### `finance/sync.py`

`sync_item()`:

1. Marks the item syncing.
2. Decrypts the access token.
3. Updates local accounts and balances.
4. Loops through Plaid transaction pages.
5. Upserts added and modified transactions.
6. Soft-deletes removed transactions.
7. Stores the next cursor.
8. Marks the item connected or records an error.

`ITEM_LOGIN_REQUIRED` changes the item to `login_required`. The task layer
skips items in that state.

### `finance/tasks.py`

`sync_accounts(item_id=None)` synchronizes one item or all items. Celery Beat
calls it every six hours.

## 9. Admin and templates

`finance/admin.py` registers every current finance model. Admin is still the
main editing surface for accounts, categories, periods, envelopes, paychecks,
bills, and budget settings.

`templates/base.html` provides:

- Navigation.
- Review count badge.
- Logout form.
- Theme toggle.
- Message display.

Page templates live in `templates/finance/`. CSS and theme JavaScript live in
`finance/static/finance/`.

## 10. How to debug a user-reported issue

Start from the user action:

### “The dashboard number is wrong”

Check:

1. `templates/finance/dashboard.html`.
2. `finance/views.py::dashboard`.
3. The relevant helper in `finance/budgeting.py`.
4. Transaction `status`, `kind`, account type, and exclusion flags.
5. `BudgetPeriod` and `Envelope` properties.
6. Tests covering `safe_cash`, `pending_forecast`, or `ready_to_assign`.

### “A transaction is missing”

Check:

1. `finance/sync.py::sync_item`.
2. `finance/plaid.py::apply_transaction`.
3. The Plaid cursor on `PlaidItem`.
4. `Transaction.is_removed`.
5. Account identifier matching.
6. Worker logs and `PlaidItem.last_sync_error`.

### “Plaid sync is stuck”

Check:

1. `docker compose ps`.
2. `docker compose logs worker beat`.
3. `PlaidItem.status`.
4. `last_sync_started_at`, `last_synced_at`, and `last_sync_error`.
5. Whether the item is `login_required`.
6. Whether Redis and the Celery worker are connected.

### “A form submission fails”

Check:

1. The POST view in `finance/views.py`.
2. CSRF token presence in the template.
3. Input parsing and `Decimal` conversion.
4. The corresponding view test.
5. Django logs and response status.

## 11. Safe contribution workflow

Before editing:

1. Read `instructions.md`.
2. Check `git status`.
3. Identify the route, view, model, template, and tests involved.
4. Look for an existing helper or pattern before adding a new one.

While editing:

- Use `Decimal` for money.
- Keep financial calculations in `finance/budgeting.py` or model properties.
- Use Django forms/validation for new user input.
- Preserve CSRF protection on POST requests.
- Do not log financial data or access tokens.
- Add migrations for model changes.
- Add tests for both normal and invalid input.
- Keep admin and user-facing behavior consistent.

Before finishing:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test finance
git diff --check
```

For Compose changes:

```bash
docker compose config --quiet
docker compose up --build
docker compose ps
```

## 12. Known architectural limitations

- 2FA is not enforced.
- Existing records are assigned to the first application user by migration;
  the migration stops rather than guessing if legacy financial data exists
  without any user.
- User-facing setup remains incomplete even though new users receive starter
  categories and budget settings automatically.
- Plaid sync has no retry/backoff or locking.
- Plaid sync does not apply categorization rules.
- Transaction list has no pagination or advanced filters.
- Many setup workflows remain admin-only.
- Removed transactions are not explicitly excluded from every query.
- Production reverse proxy and backup/restore processes are not included.
