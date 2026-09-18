# Seda Finance Deployment Guide

This guide takes a fresh clone to a security-conscious Docker deployment on a
Linux server. It assumes a single VPS, Docker Compose, a domain name, and
administrator access. It is written for the current repository state.

The application is not yet a fully hardened production product. In
particular, 2FA, multi-user ownership, automated backups, monitoring, and an
included Nginx configuration are not currently part of the repository. Treat
the steps below as a strong deployment baseline, then verify the checklist
before connecting real financial accounts.

## 1. Deployment architecture

Recommended layout:

```text
Internet
  |
  | HTTPS :443
  v
Nginx or Caddy on the host
  |
  | private HTTP connection
  v
Gunicorn in the web container :8000
  |
  +--> PostgreSQL container
  +--> Redis container
  +--> Celery worker
  +--> Celery Beat
```

Only the reverse proxy should be internet-facing. PostgreSQL and Redis should
remain on the private Docker network. The current `compose.yaml` publishes the
web service on port 8000 for local/VPS proxying, but does not publish database
or Redis ports.

## 2. Prepare the server

Use a supported 64-bit Linux VPS with enough resources for Docker, PostgreSQL,
Redis, and the Celery worker. Create a non-root deployment user and use SSH
keys instead of password authentication.

At minimum:

1. Apply operating-system security updates.
2. Create a non-root user with Docker access.
3. Disable direct root SSH login.
4. Disable SSH password authentication after verifying key login.
5. Configure a host firewall.
6. Allow only SSH, HTTP, and HTTPS from the internet.
7. Enable unattended security updates if appropriate for the operating system.
8. Configure server time synchronization.

Example firewall policy using UFW:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Do not open ports 5432 or 6379. They are internal application services.

## 3. Install required software

Install:

- Git
- Docker Engine
- Docker Compose v2 plugin
- Nginx or Caddy
- Certbot if using Nginx with Let’s Encrypt

Verify:

```bash
docker --version
docker compose version
git --version
nginx -v
```

The exact package-install commands vary by Linux distribution. Use the
official Docker documentation for the distribution rather than an unverified
installation script.

## 4. Clone the repository

Choose a deployment directory that is writable by the deployment user:

```bash
sudo mkdir -p /opt/seda-finance
sudo chown "$USER":"$USER" /opt/seda-finance
git clone <repository-url> /opt/seda-finance
cd /opt/seda-finance
```

Pin production deployments to a reviewed commit or tag rather than deploying
an arbitrary moving branch:

```bash
git fetch --all --tags
git checkout <reviewed-commit-or-tag>
```

Do not store `.env`, database dumps, access tokens, or private keys in Git.

## 5. Create production secrets

Create the environment file from the repository example:

```bash
cp .env.example .env
chmod 600 .env
```

Generate strong values with a trusted local command:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Set at least:

```dotenv
DJANGO_SECRET_KEY=<unique-long-random-value>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=finance.example.com

POSTGRES_DB=seda_financial
POSTGRES_USER=seda_finance
POSTGRES_PASSWORD=<unique-long-random-value>
REDIS_PASSWORD=<unique-long-random-value>

PLAID_CLIENT_ID=<sandbox-or-production-client-id>
PLAID_SECRET=<sandbox-or-production-secret>
PLAID_ENV=sandbox
PLAID_TOKEN_ENCRYPTION_KEY=<dedicated-secret-key-source>
```

### Plaid encryption key

The current code accepts `PLAID_TOKEN_ENCRYPTION_KEY` as a secret source and
derives a Fernet key from it. Use a separate value from
`DJANGO_SECRET_KEY`. Preserve this secret securely: losing it prevents the
application from decrypting stored Plaid access tokens.

The current implementation does not provide a key-rotation command. Document
the key location and backup procedure before storing real Plaid credentials.

### Database URL and Celery URLs

Compose constructs the internal database and Redis URLs from the
`POSTGRES_*` and `REDIS_PASSWORD` variables. Do not replace them with public
hostnames or publish those services externally.

## 6. Configure the domain and reverse proxy

Point the domain’s DNS A/AAAA record at the server. Wait for DNS propagation
before requesting a certificate.

The repository does not currently include an Nginx configuration. A minimal
reverse-proxy configuration should:

- Listen on HTTPS.
- Redirect HTTP to HTTPS.
- Proxy to `127.0.0.1:8000`.
- Overwrite `X-Forwarded-Proto` with the actual connection scheme.
- Forward the host and client IP.
- Limit request body size and proxy timeouts.
- Serve a controlled error page.

Example Nginx site:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name finance.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name finance.example.com;

    ssl_certificate /etc/letsencrypt/live/finance.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/finance.example.com/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
        proxy_read_timeout 60s;
    }
}
```

Replace the domain and certificate paths. Test before reloading:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Because Django trusts `X-Forwarded-Proto`, the reverse proxy must overwrite
the header and direct access to Gunicorn should be restricted. Do not expose
port 8000 broadly in a firewall rule.

## 7. Obtain TLS certificates

With DNS configured and port 80 open, use your chosen ACME client. For Nginx
and Certbot:

```bash
sudo certbot certonly --nginx -d finance.example.com
sudo certbot renew --dry-run
```

Install the Nginx configuration after the certificate exists, then verify:

```bash
curl -I http://finance.example.com
curl -I https://finance.example.com
```

The HTTP request should redirect to HTTPS. The HTTPS response may redirect to
`/login/` or return the login page depending on the route requested.

## 8. Validate the deployment configuration

From the repository directory:

```bash
docker compose config --quiet
docker compose build
```

Run application checks in a disposable or controlled environment:

```bash
docker compose run --rm web python manage.py check --deploy
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web python manage.py test finance
```

`check --deploy` may report expected warnings until the reverse proxy, domain,
and production secret policy are fully configured. Do not ignore warnings
without documenting why they are acceptable.

## 9. Start the application

Start all services:

```bash
docker compose up -d
```

Inspect status:

```bash
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 worker
docker compose logs --tail=100 beat
```

The expected state is:

- PostgreSQL healthy.
- Redis running.
- Web running with Gunicorn.
- Worker connected to Redis and ready.
- Beat running and scheduling.

Verify through the proxy:

```bash
curl -I https://finance.example.com/login/
```

## 10. Create the first administrator

Create an administrator interactively:

```bash
docker compose exec web python manage.py createsuperuser
```

Open:

```text
https://finance.example.com/admin/
```

Use the admin to create initial categories, budget periods, envelopes,
paychecks, recurring bills, and budget settings. The user-facing onboarding
workflow is not yet complete.

## 11. Connect Plaid safely

Start with Plaid Sandbox:

```dotenv
PLAID_ENV=sandbox
```

Confirm that:

- Plaid credentials are set only in `.env` or a secret manager.
- The application is served over HTTPS.
- The Celery worker and Redis are running.
- The dedicated Plaid encryption key is backed up securely.

Then use **Accounts → Connect account**. The application requests three months
of transaction history and queues the import in the background.

Before moving to real accounts:

1. Test account connection and reconnect behavior.
2. Verify balances and transactions manually.
3. Verify pending-to-posted behavior.
4. Verify credit-card purchases and payments are classified correctly.
5. Verify removed transactions are soft-deleted.
6. Confirm no secrets or financial values appear in logs.
7. Review current Plaid pricing, limits, and production approval requirements.

## 12. Database backups

The current repository does not provide an automated backup service. Configure
backups before using real financial data.

Create a PostgreSQL dump:

```bash
mkdir -p backups
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "backups/seda-finance-$(date -u +%Y%m%dT%H%M%SZ).dump"
chmod 600 backups/*.dump
```

The command requires the same environment values used by Compose. Do not keep
the only backup on the application host. Copy encrypted backups to separate
storage with restricted access and retention.

Back up together:

- PostgreSQL data.
- The Plaid token encryption key.
- Deployment configuration needed to restore the service.

Redis contains queue state and is not the source of truth for financial data,
but losing it can delay scheduled jobs.

## 13. Restore testing

A backup is not verified until it has been restored.

Use an isolated test Compose project or temporary PostgreSQL instance:

```bash
docker compose exec -T db sh -c \
  'createdb -U "$POSTGRES_USER" restore_test'
cat backups/<dump-file>.dump | docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d restore_test --clean --if-exists'
```

Use a disposable environment for restore testing. Never overwrite the live
database while learning the restore process.

Verify:

- Users can authenticate.
- Categories and envelopes exist.
- Transactions and Plaid item metadata exist.
- The same encryption key decrypts Plaid tokens.
- The application passes Django checks.

## 14. Updating the application

Use a reviewed commit:

```bash
cd /opt/seda-finance
git fetch --all --tags
git checkout <new-reviewed-commit-or-tag>
docker compose build
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py test finance
docker compose up -d
docker compose ps
```

The web container runs migrations before starting Gunicorn. For a higher-risk
migration:

1. Take a verified database backup.
2. Read the migration files.
3. Test the upgrade on a restored copy.
4. Deploy during a maintenance window.
5. Monitor web and worker logs.
6. Verify login, dashboard, accounts, and sync status.

Do not use `docker compose down -v` during an update. The `-v` option removes
database and Redis volumes.

## 15. Operational checks

Daily or scheduled checks should cover:

```bash
docker compose ps
docker compose logs --since=24h web
docker compose logs --since=24h worker
docker compose logs --since=24h beat
```

Watch for:

- Repeated container restarts.
- Database health failures.
- Redis authentication failures.
- Celery worker disconnects.
- Plaid `login_required` states.
- Plaid sync errors.
- Disk usage growth.
- Failed backup jobs.
- Unexpected login activity.

The application currently stores the most recent Plaid sync error on
`PlaidItem`. It does not yet provide a full operational dashboard or external
alerting integration.

## 16. Incident response basics

If credentials or tokens may be exposed:

1. Restrict access to the server.
2. Stop or isolate the affected services if necessary.
3. Rotate Django, database, Redis, Plaid, and encryption secrets as applicable.
4. Revoke or rotate Plaid items through the Plaid dashboard if required.
5. Preserve relevant logs without exposing them publicly.
6. Restore from a known-good backup if data integrity is uncertain.
7. Check for unauthorized users, account changes, and transaction changes.
8. Document the timeline and remediation.

If a Plaid item reports `ITEM_LOGIN_REQUIRED`, use the Accounts page to
reconnect it. The worker intentionally skips items in that state.

## 17. Pre-production checklist

- [ ] Server OS is patched.
- [ ] Non-root SSH access is verified.
- [ ] Root/password SSH login is disabled.
- [ ] Firewall allows only SSH, HTTP, and HTTPS.
- [ ] Docker and Compose are current and trusted.
- [ ] Repository is pinned to a reviewed commit.
- [ ] `.env` is not tracked and has mode 600.
- [ ] Django secret is unique and random.
- [ ] Database password is unique and random.
- [ ] Redis password is unique and random.
- [ ] Plaid token encryption key is separate and backed up securely.
- [ ] `DJANGO_DEBUG=False`.
- [ ] `DJANGO_ALLOWED_HOSTS` contains only the deployment hostname.
- [ ] HTTPS certificate is installed and renewal is tested.
- [ ] Reverse proxy overwrites `X-Forwarded-Proto`.
- [ ] PostgreSQL and Redis are not internet-accessible.
- [ ] `python manage.py check --deploy` warnings are reviewed.
- [ ] Database backup is configured.
- [ ] A restore test has succeeded.
- [ ] Worker and Beat are running.
- [ ] Plaid Sandbox flow has been tested.
- [ ] 2FA limitation is accepted and the application is not exposed beyond the intended trust boundary.

## 18. Keeping this guide current

Update this document whenever a change affects:

- Environment variables or secret handling.
- Docker services or ports.
- Database migrations or backup/restore.
- Reverse proxy or TLS requirements.
- Celery workers, Beat, Redis, or task scheduling.
- Plaid environments, webhooks, or sync behavior.
- Authentication, authorization, or security settings.

When a deployment behavior changes, update this guide in the same change as
the code and update `README.md` links/status if needed.
