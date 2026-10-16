# Run one shared ledger from multiple computers

This project now has two storage modes:

- **Local mode** (the original default): `gas_tracker.db` stays beside the app.
- **Shared mode**: trusted members sign in separately and edit one hosted PostgreSQL ledger. No SQLite file is copied between computers.

Shared mode uses Supabase's free hosted PostgreSQL option. At the time this was written, its Free plan includes a 500 MB database and two active projects, but a project can pause after a week of inactivity. Confirm the current limits before relying on it: [Supabase pricing](https://supabase.com/pricing) and [Free-plan billing details](https://supabase.com/docs/guides/platform/billing-on-supabase).

## Safety status

Before this redesign, a verified recovery copy was made here:

`backups/shared-redesign-2026-10-15_213549/`

It includes `gas_tracker.db`, `ledger.csv`, and `ledger.xlsx`. The backup's SQLite integrity check passed and it has the same 42 trips, 7 expenses, and 3 payments as the live local database. Do not delete it or `gas_tracker.db`.

## Owner: create the hosted workspace

1. Create a free Supabase project at [supabase.com](https://supabase.com/). The project owner—not another participant—should own it.
2. In the project dashboard, open **SQL Editor**, create a new query, paste the entire contents of [supabase_shared_schema.sql](supabase_shared_schema.sql), and run it. This enables Row Level Security before any ledger data exists.
3. Open **Settings → API** and copy the Project URL plus the **publishable** key (called the `anon` key in some dashboards). Do **not** use the `service_role` key, a Postgres password, or a direct database connection string on any participant's computer.
4. From this project folder, run:

   ```powershell
   python shared_setup.py owner
   ```

   Enter the URL/key, then either create an account or sign in with the owner's account. If Supabase requires email confirmation, confirm it, run the command again, and choose sign in.

This creates `shared_config.json`. It contains only the public project URL, publishable/anon key, and the workspace ID. It is deliberately ignored by Git.

## Owner: migrate the existing ledger once

The shared workspace must be empty. First inspect what will move:

```powershell
python migrate_to_shared.py --check
```

Then run the migration and type `MIGRATE` when asked:

```powershell
python migrate_to_shared.py
```

The migration sends the complete snapshot in one database transaction. It refuses to run against a nonempty workspace or to repeat the same migration. It checks shared event counts and balances against the local ledger afterward. It never changes or deletes the local `.db` file.

Start the desktop app normally once migration succeeds. Because `shared_config.json` exists, it will prompt for the user's own email/password and open **Shared workspace** mode. Passwords are not saved. Use **Refresh shared data** after someone else saves an entry.

## Add another person on their own computer

1. The owner runs this from their already configured project copy:

   ```powershell
   python shared_setup.py invite
   ```

   It prints a one-time code that expires after seven days.
2. Give the other person a fresh copy/clone of this project **without** `gas_tracker.db`, `backups/`, or `shared_config.json`. They should install Python plus the existing `openpyxl` dependency as needed.
3. Send them the Supabase Project URL, publishable/anon key, and one-time invite code privately. The URL/key are not an administrator secret, but they are not intended for public distribution. Never send the service-role key or database password.
4. On their computer they run:

   ```powershell
   python shared_setup.py join
   ```

   They create/sign in to their own account, enter the invite code, and the script writes their own ignored `shared_config.json`.
5. They launch the tracker, sign in, and should see the same entries and balances. Have them add a harmless test entry, use **Refresh shared data** on the owner's computer, then delete the test entry. This verifies both read and write access before daily use.

Each person can edit the central PostgreSQL database at the same time. Normal row updates are handled by the database rather than file syncing. If two people edit the exact same entry at once, the later save wins; agree before editing/deleting historical entries.

## Website publishing

The website is still static GitHub Pages output. It is not a live database viewer, so it needs a publish after ledger changes. In shared mode the app renders the page from the authenticated hosted database, then uses the same Git workflow as before.

Each person who publishes needs write access to the GitHub repository and a configured Git identity/remote. If two people publish at the same time, one Git push may be rejected; pull the current branch, then publish again. A failed website push does **not** undo the shared ledger entry.

For the least confusion, nominate one person to publish or use the owner’s computer for publishes. Everyone can still add expenses/trips from their own computer.

## Recovery and fallback

- In shared mode, **Create backup** exports the current shared ledger as CSV and XLSX. Keep those exports somewhere outside the project folder.
- Keep the original local database and the redesign backup until the shared workflow has been used successfully for a while.
- To deliberately open the retained local fallback database instead of the shared one, run this in PowerShell for that launch:

  ```powershell
  $env:GAS_TRACKER_MODE = "local"
  python gas_tracker.py
  ```

  Do not add new normal entries there after migration—the local and shared ledgers would then diverge. It is for recovery and comparison only.
- Do not store the live SQLite database in Dropbox, OneDrive, Google Drive, a shared folder, or Git. Those approaches do not provide reliable multiuser editing.
