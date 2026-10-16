# Gas & Cost Splitter

Desktop app for recording shared fuel trips, expenses, and payments. It can keep its ledger in a local SQLite database or connect to one shared Supabase workspace.

## Start the app

1. Install **Python 3.10 or later** on Windows and make sure `python` and `pythonw` are available on PATH.
2. Install the app's Python dependency:

   ```powershell
   python -m pip install openpyxl
   ```

3. Double-click `Launch Gas Tracker.bat`.

If the app does not open, run `python gas_tracker.py` from this folder in PowerShell to see startup errors. The launcher uses `pythonw`, which does not open a console window.

## Choose where data is stored

### Local mode (default)

The app stores the ledger in `gas_tracker.db` beside the application. On first launch, if `407.xlsx` is present, the app imports the supported historical rows once and never edits the workbook. It records that import in the database to avoid importing the same rows again.

Keep the database and backups private:

- `gas_tracker.db` is the live local ledger.
- **Settings & Backup → Create database backup** saves a timestamped SQLite backup and CSV/XLSX ledger exports under `backups/`.
- **Export ledger to CSV** creates a standalone human-readable ledger export.
- Do not put the live SQLite database in OneDrive, Dropbox, Google Drive, Git, or another synchronized folder to share it. SQLite file syncing is not multiuser database access.

### Shared Supabase mode (optional)

For multiple computers editing one ledger, configure a shared workspace by following [SHARED_DATABASE_SETUP.md](SHARED_DATABASE_SETUP.md). Once `shared_config.json` is present, the launcher selects shared mode and prompts each user to sign in. The app stores the public project URL/key and workspace ID in that ignored config file; it does not save the user's password.

Shared mode requires an internet connection. Use **Refresh shared data** to fetch changes made by another member. The app does not automatically merge data into the local `gas_tracker.db`; that file remains a separate fallback. Set `GAS_TRACKER_MODE=local` for a launch when you intentionally need that fallback.

The shared mode's **Create database backup** action exports CSV and XLSX files; it cannot create a SQLite copy of the hosted database. Keep those exports and any separate Supabase recovery backups.

## Record and review costs

1. **Add Trip** records kilometres, driver, people who went, and the gas price in cents per litre. Leave the price blank if it is unknown; the trip is excluded from balances until priced. **Fill pending gas prices** applies a price to all still-unpriced trips.
2. **Add Expense** records shared costs such as tolls, food, and parking.
3. **Record Payment** records money actually sent between two people; it adjusts balances without changing the original expenses.
4. **Dashboard** shows each person's balance and suggested settlements. **Activity** lets you inspect, edit, or delete saved entries. **Owed costs** shows the active expense shares behind current balances.
5. The payer is credited for the full cost, and the selected attendees are charged equal shares. If the split leaves an extra cent, it is assigned to a non-payer first. Each trip stores its own fuel-efficiency value, so changing the default later does not rewrite old trips.

Before deleting or making substantial changes, create a backup/export. Deletions cannot be undone except by restoring a backup.

## Expense requests from the public page

The published page includes a **Suggest an expense** form. It only downloads a JSON request file in the visitor's browser; it does not write to the ledger or connect to Supabase. Send that file to a tracker member, who can use **Expense Requests → Import request file** to review it. **Add selected** approves it into the ledger; **Delete selected** rejects it. Duplicate request files are ignored.

## Publish the read-only page

The web page is a **static snapshot**, not a live database viewer. It includes names, balances, dates, descriptions, notes, and expense details; publish it only if everyone is comfortable with that information being public. See [DEPLOY_READONLY_WEB.md](DEPLOY_READONLY_WEB.md) for GitHub Pages setup and privacy guidance.

- In local mode, run `python publish_readonly.py` to render `docs/index.html` from the local database.
- In shared mode, use **Publish now** in the desktop app so it renders from the signed-in Supabase workspace. Running `publish_readonly.py` directly reads the local SQLite database instead.
- The app's publish action creates timestamped backup exports when the page changes, then commits and pushes the snapshot to the current branch on `origin`. Git must be installed, a remote must be configured, and the current account must have push access.
- If two people publish simultaneously, one push can be rejected; sync the current branch and try again.

## Troubleshooting and verification

- Check a local database and the pending shared migration without sending data:

  ```powershell
  python migrate_to_shared.py --check
  ```

- Verify shared sign-in and read access:

  ```powershell
  python shared_setup.py verify
  ```

- The shared database schema must be installed in Supabase before setup. If the app reports a missing table/function or schema-cache error, verify that [supabase_shared_schema.sql](supabase_shared_schema.sql) was run in the correct project.
- Keep the local database and the pre-migration recovery backup until the shared workflow has been tested successfully. Follow the migration checks in [SHARED_DATABASE_SETUP.md](SHARED_DATABASE_SETUP.md); do not migrate into a nonempty workspace.
