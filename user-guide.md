# Seda Finance User Guide

This guide describes how to use the current application. It assumes the
application is running and you already have a user account.

The current release supports separate user accounts with per-user financial
data isolation, uses USD-style amounts, and is still an early release. Plaid
connection currently targets Plaid Sandbox.

## 1. Sign in

Open the application URL and sign in with your Django account.

Typical local URL:

```text
http://localhost:8000/
```

After signing in, you land on the Dashboard.

If you cannot sign in:

- Confirm the application is running.
- Confirm your username and password.
- An administrator can reset the password from `/admin/`.

Two-factor authentication is not implemented yet. Do not expose the current
application publicly until production security hardening is complete.

Each user has a separate set of accounts, transactions, categories, budgets,
paychecks, bills, rules, and Plaid connections. A user cannot access another
user's records through the finance pages or POST actions.

## 2. Understand the main navigation

The top navigation contains:

- **Dashboard**: cash, safe-to-spend, budget, and recent activity.
- **Review**: transactions waiting for classification.
- **Transactions**: searchable transaction history.
- **Budget**: monthly envelope assignments and spending.
- **Planning**: expected paychecks, recurring bills, and envelope balances.
- **Rules**: merchant categorization rules.
- **Accounts**: connected accounts, Plaid status, and manual sync.

The review badge shows how many transactions currently need attention.

## 3. Initial setup through Admin

When a new Django user is created, Seda Finance automatically provisions the
starter categories and that user's budget settings. Financial records created
afterward must belong to that user.

Several setup actions are currently performed in Django admin.

Open:

```text
/admin/
```

Recommended first-time order:

1. Review starter categories.
2. Create a budget period.
3. Create envelopes for the categories you budget.
4. Add expected paychecks.
5. Add recurring bills.
6. Configure base-pay and surplus settings.
7. Connect accounts through the Accounts page.

## 4. Starter categories

The first finance migration creates:

- Housing
- Utilities
- Groceries
- Dining
- Transportation
- Healthcare
- Subscriptions
- Personal
- Savings
- Debt payments
- Investing
- Other

To customize them:

1. Open `/admin/`.
2. Select **Finance → Categories**.
3. Rename or add categories.
4. Set **Is envelope** for categories that should participate in the budget.
5. Enable **Rollover enabled** for categories such as Car Repairs or Savings
   where unused money should carry forward.
6. Keep inactive categories only if they should no longer be used for new
   planning.

Avoid deleting categories that already have transactions or envelopes. The
database protects many historical relationships.

## 5. Create a monthly budget period

Budget periods are calendar-month ranges.

To create one:

1. Open `/admin/`.
2. Select **Finance → Budget periods**.
3. Create a row with:
   - Start date, such as the first day of the month.
   - End date, such as the last day of the month.
   - Reset day, normally `1`.
4. Save it.
5. Open **Finance → Envelopes**.
6. Create one envelope for each budget category in that period.

The current application displays the newest budget period as the active period.

## 6. Connect bank and credit-card accounts

### Configure Plaid Sandbox

Before connecting an account, the operator must configure:

```text
PLAID_CLIENT_ID
PLAID_SECRET
PLAID_ENV=sandbox
```

These belong in `.env`, not in source code or chat messages.

Restart the application after changing environment variables.

### Connect from Accounts

1. Open **Accounts**.
2. Select **Connect account**.
3. Complete the Plaid Link flow.
4. Choose the Sandbox institution and test credentials.
5. Finish the connection.

The application then:

1. Exchanges the Plaid public token.
2. Stores an encrypted access token.
3. Imports account names, types, masks, and balances.
4. Queues a three-month transaction import.

The initial import runs in the background. Keep the worker and Redis services
running.

### Account types

The application recognizes:

- Checking
- Savings
- Credit card

Checking and savings contribute to cash possession. Credit-card balances are
shown separately and are not added to positive cash.

## 7. Understand account sync status

Each connected Plaid item can show:

- **Connected**: available for synchronization.
- **Syncing**: a background sync is running.
- **Reconnect required**: Plaid requires the institution login again.
- **Sync error**: the last sync failed for another reason.

Use **Sync now** to queue a manual sync.

Automatic synchronization is scheduled every six hours by Celery Beat.

If the item says **Reconnect required**:

1. Start the account connection flow again.
2. Complete Plaid Link for the institution.
3. Wait for the new background sync.

## 8. Review imported transactions

Open **Review** after the first sync.

Each transaction starts with `Needs review` unless it was manually classified
or updated by an existing workflow.

Select one or more rows, then choose a classification:

### Expense

Choose a category. The transaction then counts toward that envelope once it is
posted and not excluded from the budget.

### Income

Use this for paychecks, refunds treated as income, or other money received.
Income does not reduce an envelope.

### Transfer

Use this for money moving between accounts, including credit-card payments.
Transfers do not count as category spending.

The current review action applies one classification to all selected rows.
Use separate selections when transactions need different categories.

## 9. Credit-card payments and spending

The intended behavior is:

- A credit-card purchase is an expense when posted.
- The purchase reduces its category envelope.
- The later payment from checking to the card is a transfer.
- The payment does not reduce the category a second time.

Until automatic transfer detection is implemented, classify credit-card
payments manually as transfers in the Review screen or admin.

## 10. Use the Transactions page

Open **Transactions** to search transaction history.

The current search checks:

- Merchant name.
- Notes.
- Account name.

Example searches:

```text
grocery
rent
checking
subscription
```

The current page does not yet provide advanced date, category, status, or
pagination controls.

## 11. Build the monthly budget

Open **Budget**.

The page displays:

- **Posted income**: income transactions that have posted inside the period.
- **Expected income**: planned paycheck amounts for the period.
- **Ready to Assign**: received income and rollover money not yet assigned.
- **Assigned**: amount given to each envelope.
- **Spent**: posted categorized expenses in that category.
- **Remaining**: assigned plus rollover minus spent.

### Assign money

1. Enter the amount for each envelope.
2. Review the total available money.
3. Select **Save assignments**.

The application records changes as budget allocation events for auditability.

Assigned amounts cannot be negative or invalid text.

### Overspending

An envelope becomes overspent when remaining money is below zero. Overspending
is displayed as a warning but does not block transactions.

### Important cash rule

Expected income helps you plan, but it does not count as received cash or
Ready to Assign until a posted income transaction exists.

## 12. Plan around biweekly paychecks

Open **Planning**.

The current page shows:

- Expected income for the current month.
- Expected and received paychecks.
- Recurring bills.
- Remaining envelope balances.

Paychecks and bills are currently created through the admin links on the page.

### Add an expected paycheck

1. Open `/planning/`.
2. Select the expected paychecks **Manage** link.
3. Create a paycheck with:
   - Pay date.
   - Expected amount.
   - Expected status.
4. Save it.

When the actual paycheck arrives, update the record to **Received** and enter
the received amount. The received amount then replaces the expected amount in
planning calculations.

This supports overtime or a smaller-than-expected paycheck without pretending
the estimate was received.

### Add a recurring bill

1. Open `/planning/`.
2. Select the recurring bills **Manage** link.
3. Create a bill with:
   - Name.
   - Category.
   - Expected amount.
   - Due day from 1 through 31.
   - Essential flag.
   - Active flag.
4. Save it.

Bills due on day 31 are clamped to the last day in shorter months for reserve
calculations.

## 13. Understand cash and safe-to-spend

The Dashboard shows several different concepts.

### Cash balance

The total current balance of checking and savings accounts.

Credit-card accounts are not added to this number.

### Safe to spend

Cash balance minus pending expense outflows from checking and savings.

This is a conservative cash estimate and not a guarantee that every bill has
been reserved.

### Forecast cash

Safe cash plus pending income.

Pending income is shown for forecasting only. It does not become official
income until it posts.

### Envelope remaining

The amount left in an envelope after posted categorized expenses.

Use both safe cash and envelope remaining:

- Safe cash answers “How much money is physically available?”
- Envelope remaining answers “How much of a category’s budget remains?”

## 14. Adjust money mid-month

When a real-life change happens, use this workflow.

### Reassign money between envelopes

1. Open **Budget**.
2. Reduce the original envelope.
3. Increase the destination envelope.
4. Save.
5. Confirm the new remaining amounts.

The difference is recorded as budget allocation events.

### Add newly received income

1. Confirm the Plaid income transaction is posted.
2. Classify it as **Income** in Review if needed.
3. Return to Budget.
4. Confirm Ready to Assign increased.
5. Assign the new money to envelopes.

### Handle a lower paycheck

1. Update the paycheck with the actual received amount.
2. Mark it Received.
3. Review cash and envelope balances.
4. Reduce discretionary envelopes such as Dining or Personal manually.
5. Do not assume expected income is available.

Automatic shortfall recommendations are not implemented yet, so the app does
not automatically move money from savings or reduce categories.

### Handle overtime

1. Mark the paycheck Received.
2. Enter the actual amount.
3. Compare it with the expected/base amount in your planning process.
4. Assign the extra money manually to responsibilities, savings, investing, or
   discretionary spending.

The percentage settings are stored in Budget Settings, but automatic surplus
splitting is not implemented yet.

## 15. Create categorization rules

Open **Rules**.

Create a rule with:

- Rule name.
- Merchant pattern.
- Contains or exact matching.
- Category.
- Optional account.
- Suggest-only or auto-apply behavior.

Rules are currently stored and displayed. Automatic application during Plaid
sync is not yet connected, so review imported transactions manually until that
feature is implemented.

## 16. Troubleshooting

### The application is unavailable

Check the services:

```bash
docker compose ps
docker compose logs web
docker compose logs worker
docker compose logs beat
```

Rebuild after dependency or Docker changes:

```bash
docker compose up --build
```

### Plaid connection button is missing

Confirm `.env` contains:

```text
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=sandbox
```

Then restart the web service.

### Transactions did not arrive

Check:

1. The worker is running.
2. Redis is running.
3. The Plaid item status on Accounts.
4. `last_sync_error` in admin if the item failed.
5. Whether the item needs reconnection.

### Budget spending looks wrong

Confirm the transaction:

- Is posted.
- Is classified as an expense.
- Has the expected category.
- Is not excluded from budget.
- Is not a transfer or income transaction.

### A payment counted as spending twice

Classify the account payment as a transfer. The purchase should remain the
expense that reduces the category envelope; the payment should not be another
expense.

## 17. Current limitations

The following features are not complete:

- Two-factor authentication.
- Multi-user accounts and per-user data isolation.
- Production Plaid credentials and live-bank validation.
- Plaid webhooks.
- Automatic rule application during sync.
- Automatic transfer detection.
- Full in-app setup forms.
- Automatic paycheck matching.
- Automatic surplus/shortfall recommendations.
- Advanced transaction filtering and pagination.
- Full rollover-period automation.
