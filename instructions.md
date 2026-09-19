# Personal Finance App — Specification

## 1. Overview

A self-hosted personal finance app that connects to bank and credit card
accounts via Plaid, tracks all spending/earning in one place, and uses a
zero-based (envelope) budgeting model. New transactions are categorized
by a rules engine, with low-confidence matches routed to a manual review
queue. Must be comfortably usable from a mobile browser.

## 2. Goals

- Single source of truth for spending, income, and account balances
  across all connected accounts.
- Zero-based budgeting: every dollar of income is assigned to a
  category/envelope; nothing is "unbudgeted."
- Fast triage of new transactions via rules, with a review queue for
  anything the rules don't confidently handle.
- Works well on a phone browser — no native app required.

## 3. Non-Goals (for v1)

- Multi-user support (single-user app, at least initially).
- Investment/brokerage account tracking (Plaid supports this, but it's
  a separate data model — defer to a later version).
- Bill pay / money movement — this is read-only tracking, not a
  transactional app.
- Native iOS/Android apps.

## 4. Core Concepts & Data Model

### Accounts
- Synced from Plaid: checking, savings, credit card.
- Fields: institution name, account name/mask, type, current balance,
  available balance, last synced timestamp.

### Transactions
- Synced from Plaid on a schedule (see §6).
- Fields: date, merchant name (raw from Plaid), amount, account,
  pending/posted status, category (nullable until categorized),
  rule applied (nullable), notes (user-editable), excluded-from-budget
  flag (for things like credit card payments that would double-count
  spending).
- Plaid transaction ID stored to dedupe on re-sync.

### Categories
- User-defined, flat list to start (e.g., Groceries, Rent, Dining,
  Subscriptions). Nested categories are a nice-to-have, not required
  for v1.
- Each category can be marked as an "envelope" that participates in
  the zero-based budget.

### Envelopes / Budget (zero-based model)
- Each budget period (monthly, resets on a configurable day), total
  income is allocated across envelopes until $0 remains unassigned.
- Each envelope has: assigned amount, spent amount (sum of categorized
  transactions in that category for the period), remaining amount.
- Overspending an envelope should visibly flag it (not block anything —
  this is a tracking tool, not an enforcement tool).
- Unassigned income should be clearly visible as its own line ("Ready
  to Assign") so the user always sees if money hasn't been given a job.
- Rolling over unspent envelope balances into the next period should be
  configurable per-category (e.g., "Car Repairs" rolls over, "Dining"
  does not).

### Rules
- User-created rules like "merchant contains 'Walmart' → Groceries."
- Match fields: merchant name (contains/exact), amount range (optional),
  account (optional).
- Each rule has a confidence behavior:
  - **Auto-apply**: matches are categorized immediately on sync, no
    review needed.
  - **Suggest only**: matches are pre-filled with the suggested
    category but land in the review queue for confirmation.
- Default new rules to "suggest only" until the user has confirmed a
  handful of matches, then offer to promote it to auto-apply. (This
  avoids silent miscategorization from an overly broad rule.)

### Review Queue
- Landing view after login: all uncategorized transactions, plus any
  "suggest only" rule matches awaiting confirmation.
- Bulk actions: select multiple transactions, assign to a category,
  optionally create a rule from the selection in one step.

## 5. Plaid Integration

- Plaid Link for connecting accounts (handles bank auth/MFA directly;
  the app never sees or stores bank credentials).
- Store Plaid `access_token` per item, encrypted at rest.
- Transaction sync via Plaid's `/transactions/sync` endpoint (cursor-based,
  handles adds/updates/removals cleanly rather than re-fetching full history).
- Handle Plaid `ITEM_LOGIN_REQUIRED` errors gracefully — surface a
  "reconnect this account" prompt rather than failing silently.
- Confirm current Plaid pricing/limits for personal use before
  committing accounts — free tier limits change and should be checked
  at build time, not assumed from this spec.

## 6. Sync Behavior

- Scheduled background sync (e.g., every few hours via a cron job /
  Celery beat task) rather than only syncing on login, so balances are
  current when the user checks in.
- Manual "sync now" option on the dashboard.
- New transactions from a sync run through the rules engine
  automatically: auto-apply rules categorize immediately, everything
  else (no rule match, or "suggest only" match) lands in the review
  queue.

## 7. UI / Screens

- **Dashboard**: current envelope balances, "Ready to Assign" amount,
  account balances, recent activity.
- **Review Queue**: uncategorized + pending-confirmation transactions,
  with bulk categorize and "create rule from this" actions.
- **Transactions**: full searchable/filterable history across accounts.
- **Budget**: envelope list for the current period, assign/edit amounts,
  rollover settings per category.
- **Rules**: list/create/edit rules, see which transactions each rule
  has matched historically.
- **Accounts**: connected accounts, balances, reconnect/remove.

## 8. Mobile Requirements

- Responsive layout that works cleanly in a mobile browser — no
  installable PWA or native wrapper required for v1.
- Review Queue and Dashboard are the two screens most likely to be
  used on mobile; prioritize those layouts first.

## 9. Security Requirements

- Encrypt Plaid access tokens and any stored financial data at rest.
- Require authentication (password + 2FA) to access the app at all,
  given the sensitivity of the data.
- Session timeout / auto-logout after inactivity.
- HTTPS only, via the existing Nginx reverse proxy setup.
- No financial data in logs.

## 10. Suggested Stack

- **Backend**: Django + PostgreSQL (use `DecimalField`/`numeric` for
  all monetary values — never floats).
- **Background jobs**: Celery + Redis (or Django-Q as a lighter-weight
  alternative) for scheduled Plaid syncs.
- **Frontend**: Django templates + HTMX for interactivity (review
  queue bulk actions, live envelope updates) without a separate
  frontend build step.
- **Auth**: Django built-in auth + `django-otp` for 2FA.
- **Deployment**: Docker Compose + Nginx reverse proxy (matches
  existing VPS setup).

## 11. Open Questions / Assumptions Made

These weren't specified — noted here so they're visible rather than
silently decided:

- **Historical data**: How far back should the initial Plaid sync
  pull transactions? (Plaid typically offers up to 24 months.)
- **Multiple budget "owners"**: Financial records are now owned by the
  authenticated Django user. Shared household budgeting is still a future
  feature and would require explicit household membership rules.
- **Recurring transaction / subscription detection**: Not specified —
  worth deciding if you want the app to flag recurring charges
  (subscriptions, etc.) automatically, or if that's out of scope.
- **Net worth / savings goals tracking**: Not specified — separate from
  monthly budgeting, would need its own section if wanted.
- **Currency**: Assumed single-currency (USD) — flag if that's wrong.
- **Credit card payments**: Need a rule for excluding credit card
  payments from spending totals (otherwise a payment shows up as both
  a "expense" on checking and would double-count against categories
  if not handled carefully).
