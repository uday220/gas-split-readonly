# Gas & Cost Splitter

Double-click `Launch Gas Tracker.bat` to open the desktop app. It uses only local files:

- `gas_tracker.py` — the application
- `gas_tracker.db` — your live data (created when first opened)
- `backups/` — copies created with the in-app backup button
- `407.xlsx` — your original spreadsheet; the app reads it once and never edits it

On first launch, the app imports the 20 spreadsheet rows. It treats the 407 row as the `$73.04` toll recorded in the formula, and imports the May 26 Cost Split as an `$88.52` food expense paid by Uday and shared by Uday and Gurpreet.

## Daily use

1. Use **Add Trip** for normal drives. Use the **Pick** button to choose a date from the mini calendar, enter the distance and current price in cents per litre, then select everyone who went. If the price is unknown, leave it empty: the trip is shown as `price pending` and is not included in balances until you add it.
2. Use **Add Expense** for tolls, food, parking, or any other shared purchase.
3. Use **Record Payment** only when somebody actually sends money to someone else.
4. The dashboard says who should receive or pay, and gives the fewest settlement payments needed.

Use **Activity** to inspect any entry. Select it and choose **Edit selected** (or double-click it) to correct the date, payer, people, amount, notes, or a gas price entered later. If you fill up and know one gas price should apply to every trip that is still waiting, use **Fill pending gas prices** in Activity to update them all at once.

## Share a read-only web view

Run `py publish_readonly.py` to generate `docs/index.html`, a static page with no editing controls or database access. See [DEPLOY_READONLY_WEB.md](DEPLOY_READONLY_WEB.md) for the GitHub Pages deployment steps and privacy checklist.

Costs are transparent: the payer receives credit for the full amount, and every selected participant pays one equal share. If a split has an unavoidable extra cent, it is charged to a non-payer first, so the person who fronted the money is never short-changed. Each trip stores the fuel efficiency used when it was entered, so changing a car's mileage later does not rewrite history. The dashboard's `Ledger check` should always read `Balanced`.

Before changing major settings or deleting entries, create a database backup from **Settings & Backup**. The same tab can export a full human-readable ledger to CSV.

Every time the app publishes the read-only web snapshot, it also creates a timestamped backup bundle in `backups/` with the SQLite database plus CSV and XLSX ledger exports.
