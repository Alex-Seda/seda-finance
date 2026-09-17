# Seda Finance

Seda Finance is a self-hosted personal finance application for consolidating bank and credit-card accounts, categorizing transactions, and managing a zero-based envelope budget.

The project is currently an early-stage Django scaffold. The web interface, budgeting data model, review queue, categorization rules, authentication, Docker Compose environment, and Django admin are in place. Plaid Link and live transaction synchronization are intentionally not included yet.

## Features

- Responsive Django templates for desktop and mobile browsers
- Dashboard with account balances, envelope status, recent activity, and review counts
- Transaction review queue with bulk categorization
- Searchable transaction history
- Zero-based budget periods and category envelopes
- Configurable envelope rollover settings
- Merchant categorization rules with suggest-only and auto-apply modes
- Django authentication protecting all application pages
- Custom light/dark/automatic theme shared by the application and admin
- Django admin theme matching the main application
- PostgreSQL, Redis, Celery worker, and Celery beat services through Docker Compose
- SQLite fallback for quick local development without containers

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
| `PLAID_CLIENT_ID` | Reserved for the future Plaid integration |
| `PLAID_SECRET` | Reserved for the future Plaid integration |
| `PLAID_ENV` | Reserved Plaid environment setting |

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

1. **Create categories.** Use **Admin → Finance → Categories** to create categories such as Groceries, Rent, Dining, and Subscriptions. Mark budget categories as envelopes and enable rollover where appropriate.
2. **Create a budget period.** Use **Admin → Finance → Budget periods**, then create one envelope per budgeting category under **Admin → Finance → Envelopes**.
3. **Review the budget.** Open `/budget/` to update assigned amounts and see spent and remaining amounts.
4. **Add transactions.** Until Plaid integration is available, add them through **Admin → Finance → Transactions**.
5. **Categorize transactions.** Leave new transactions marked for review, then open `/review/` and bulk-assign categories.
6. **Add rules.** Open `/rules/` to create merchant matching rules. New rules default to suggest-only behavior.
7. **Search activity.** Open `/transactions/` to search transaction history.
8. **Manage accounts.** Open `/accounts/` for the account overview. Account connection through Plaid is planned but not implemented.

## Application URLs

| URL | Description |
| --- | --- |
| `/` | Authenticated dashboard |
| `/login/` | Login page |
| `/logout/` | Logout endpoint |
| `/review/` | Transaction review queue |
| `/transactions/` | Searchable transaction history |
| `/budget/` | Envelope budget management |
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

- Plaid Link and encrypted Plaid access-token handling are not implemented.
- Automatic Plaid transaction and balance synchronization is not implemented.
- The Celery sync task is currently a placeholder.
- Account and transaction creation is currently performed through Django admin.
- Two-factor authentication, production HTTPS configuration, and deployment hardening still need to be completed.
- The application is designed for a single user in its current form.

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
