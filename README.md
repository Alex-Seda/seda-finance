# Seda Finance

Seda Finance is a self-hosted personal finance application for consolidating bank and credit-card accounts, categorizing transactions, and managing a zero-based envelope budget.

The project is currently an early-stage Django application. The web interface, budgeting data model, paycheck planning, recurring-bill planning, review queue, categorization rules, authentication, Docker Compose environment, migrations, Django admin, and a Plaid Sandbox integration are in place. Production Plaid use and deployment hardening are not complete.

## Features

- Responsive Django templates for desktop and mobile browsers
- Dashboard with account balances, envelope status, recent activity, and review counts
- Transaction review queue with bulk categorization
- Searchable transaction history
- Zero-based calendar-month budget periods and category envelopes
- Biweekly paycheck planning with expected income, conservative base pay, and recurring bills
- Safe-to-spend cash view based on checking/savings balances minus pending outflows
- Manual transaction classification for expenses, income, and transfers
- Posted-only budget spending with pending-transaction cash forecasting
- Auditable envelope allocation events
- Plaid Sandbox Link flow with encrypted access tokens
- Background Plaid transaction synchronization with cursor tracking
- Soft-deletion of removed Plaid transactions
- Account sync status and manual “Sync now” queueing
- Configurable envelope rollover settings
- Merchant categorization rules with suggest-only and auto-apply modes
- Django authentication protecting all application pages
- Custom light/dark/automatic theme shared by the application and admin
- Django admin theme matching the main application
- PostgreSQL, Redis, Celery worker, and Celery beat services through Docker Compose
- SQLite fallback for quick local development without containers

## Current implementation status

The application currently supports the v1 financial foundation and is still
intended for local development or controlled testing. It does **not** yet
connect to a bank, import transactions automatically, or provide production
security hardening.

Implemented now:

- Authenticated dashboard, budget, planning, review, transaction, rules, and account pages
- Single-user USD-oriented data model
- Calendar-month budget periods
- Posted income and Ready to Assign calculations
- Expected paycheck records with received-versus-expected amounts
- Paycheck allocation records
- Recurring bills with due days and expected amounts
- Manual expense, income, and transfer classification
- Cash balance and safe-to-spend calculations using checking/savings balances minus pending expense outflows
- Credit-card accounts excluded from the positive cash total
- Starter category migration
- Django admin management for all current models
- Automated finance tests for accounting calculations, validation, authentication, and core POST workflows
- Fake-provider tests for token encryption, Plaid account/transaction sync, removals, and `ITEM_LOGIN_REQUIRED`

Not implemented yet:

- Automatic transaction rule processing during Plaid sync
- Automatic transfer detection
- Automatic paycheck matching
- Automatic shortfall recommendations or surplus splitting
- In-app onboarding and forms for creating accounts, paychecks, bills, and budget periods
- Two-factor authentication
- Production HTTPS, Nginx, backups, monitoring, and deployment hardening

## Requirements

- Python 3.12 or newer
- Docker Engine and Docker Compose v2 for the full stack
- Git

## Quick start with Docker Compose

Clone the repository and start the services:

```bash
docker compose up --build
```

The application will be available at <http://127.0.0.1:8000/>.

Compose starts:

| Service | Purpose |
| --- | --- |
| `web` | Django development server |
| `db` | PostgreSQL database |
| `redis` | Celery broker and result backend |
| `worker` | Background task worker |
| `beat` | Scheduled task runner |

The web container runs migrations before starting Django. PostgreSQL and Redis data are stored in named Docker volumes.

To stop the stack:

```bash
docker compose down
```

To stop it and remove the local database and queue data:

```bash
docker compose down -v
```

## Local development without Docker

Create a virtual environment and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Apply migrations and start Django:

```bash
python manage.py migrate
python manage.py runserver
```

With no `DATABASE_URL` set, Django uses `db.sqlite3` locally. Set `DJANGO_DEBUG=False` explicitly for a non-development deployment.

Run the application checks and tests:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test finance
```

## Configuration

Copy the example environment file when using Compose or custom settings:

```bash
cp .env.example .env
```

`.env` is ignored by Git. Never commit real credentials, access tokens, or production secrets.

Important settings include:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django signing and cryptographic secret |
| `DJANGO_DEBUG` | Enables or disables Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames |
| `DATABASE_URL` | Optional PostgreSQL connection URL |
| `POSTGRES_DB` | PostgreSQL database name for Compose |
| `POSTGRES_USER` | PostgreSQL username for Compose |
| `POSTGRES_PASSWORD` | PostgreSQL password for Compose |
| `CELERY_BROKER_URL` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | Celery result backend URL |
| `PLAID_CLIENT_ID` | Plaid client ID |
| `PLAID_SECRET` | Plaid API secret; keep it in `.env` and never commit it |
| `PLAID_ENV` | Plaid environment, currently `sandbox` |
| `PLAID_TOKEN_ENCRYPTION_KEY` | Optional dedicated Fernet key source; when empty, the access-token encryption key is derived from `DJANGO_SECRET_KEY` |

## First login and administration

The project does not ship with a default administrator. Create one in the database used by your environment:

```bash
python manage.py createsuperuser
```

For the Compose database:

```bash
docker compose exec web python manage.py createsuperuser
```

The main application is at `/`. The Django admin is at `/admin/`. All finance pages require authentication.

## Using the application

1. **Create an administrator.** Run `python manage.py createsuperuser`, then sign in at `/admin/`.
2. **Review starter categories.** The first migration creates Housing, Utilities, Groceries, Dining, Transportation, Healthcare, Subscriptions, Personal, Savings, Debt payments, Investing, and Other. Customize them under **Admin → Finance → Categories** and mark budget categories as envelopes.
3. **Create a budget period.** Use **Admin → Finance → Budget periods**, then create one envelope per budgeting category under **Admin → Finance → Envelopes**.
4. **Set up planning.** Add expected biweekly paychecks and recurring bills under `/planning/` using the admin links. Configure the manual base paycheck and surplus percentages under **Admin → Finance → Budget settings**.
5. **Review the budget.** Open `/budget/` to update assignments and see posted income, expected income, Ready to Assign, spent, and remaining amounts.
6. **Add transactions.** Until Plaid integration is available, add them through **Admin → Finance → Transactions**. Set each transaction's kind explicitly when it is income or a transfer.
7. **Categorize transactions.** Leave new transactions marked for review, then open `/review/` and classify selected items as expenses, income, or transfers. Expense items can be bulk-assigned to a category.
8. **Add rules.** Open `/rules/` to create merchant matching rules. New rules default to suggest-only behavior.
9. **Search activity.** Open `/transactions/` to search transaction history.
10. **Manage accounts.** Open `/accounts/` for the cash/debt account overview.
11. **Connect Plaid Sandbox accounts.** Set `PLAID_CLIENT_ID`, `PLAID_SECRET`, and `PLAID_ENV=sandbox` in `.env`, restart the web and worker services, then use **Accounts → Connect account**. The initial three-month transaction history is queued in the background. Plaid items are scheduled for synchronization every six hours.

## Application URLs

| URL | Description |
| --- | --- |
| `/` | Authenticated dashboard |
| `/login/` | Login page |
| `/logout/` | Logout endpoint |
| `/review/` | Transaction review queue |
| `/transactions/` | Searchable transaction history |
| `/budget/` | Envelope budget management |
| `/planning/` | Expected paycheck and recurring bill planning |
| `/rules/` | Categorization rule management |
| `/accounts/` | Account overview |
| `/admin/` | Django administration |

## Project structure

```text
config/                 Django project settings, URLs, WSGI, and Celery
finance/                Finance models, views, admin, tasks, and static assets
finance/migrations/     Database migrations
templates/              Application and admin templates
compose.yaml            Local multi-container environment
Dockerfile              Django application image
manage.py               Django management entry point
requirements.txt        Python dependencies
```

## Current limitations

- Production Plaid credentials, webhook support, and live-bank validation are not implemented.
- Automatic transaction rule processing during Plaid sync is not implemented.
- Account and transaction creation is currently performed through Django admin unless connected through Plaid.
- Two-factor authentication, production HTTPS configuration, and deployment hardening still need to be completed.
- The application is designed for a single user in its current form.
- The paycheck planner currently stores expected paychecks, allocations, recurring bills, and base-pay settings; automatic paycheck matching and cash-flow recommendations are still pending.
- The current web UI exposes planning and review workflows, but creation and editing of accounts, paychecks, bills, budget periods, envelopes, and base-pay settings still happens through Django admin.
- Plaid Link currently supports Sandbox account connection, three-month history requests, account/balance sync, cursor-based transaction adds and modifications, soft-deleted removals, manual sync queueing, and reconnect-required status. Webhooks, production credentials, and automatic rule application during sync are not implemented.

## Security notes

This application handles sensitive financial information. Before deploying it outside local development:

- Set a strong, unique `DJANGO_SECRET_KEY`.
- Set `DJANGO_DEBUG=False`.
- Use a managed or properly secured PostgreSQL instance.
- Configure HTTPS behind a reverse proxy.
- Do not commit `.env`, database files, access tokens, or credentials.
- Add and verify two-factor authentication before exposing the application publicly.
- Review logging and backups to ensure financial data and secrets are not exposed.

## License

No license has been selected yet. Until a license is added, the repository should not be treated as granting permission to reuse the code.
