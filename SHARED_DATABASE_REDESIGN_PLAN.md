# Shared database redesign plan

## Goal

Allow trusted people on separate computers to edit one authoritative gas ledger,
without copying or synchronising the SQLite file. The existing local tracker
must remain usable and untouched until the shared version is confirmed.

## Chosen free service

Use a free Supabase project: hosted PostgreSQL plus account-based access. The
desktop program talks to Supabase's REST API with each person's own sign-in;
the PostgreSQL password is never copied to the other computers. Supabase's
Free plan currently includes a 500 MB PostgreSQL database and two active free
projects, but inactive projects can pause. See the official references in
`SHARED_DATABASE_SETUP.md` before relying on it.

## Safety gates

1. **Backup first — complete.** A verified database, CSV and XLSX export were
   created in `backups/shared-redesign-2026-10-15_213549/`. It contains the
   same 42 trips, 7 expenses and 3 payments as the live database.
2. Leave `gas_tracker.db` in place. It remains the fallback and is never
   modified by the migration utility.
3. Create and test the empty hosted workspace before migrating any data.
4. Migrate once, compare event counts and balances, then have a second person
   sign in and verify they see the same ledger.
5. Only after that, switch normal daily use to shared mode. Retain the local
   file and the export backup.

## Implementation

- [x] Preserve and verify a pre-redesign backup.
- [x] Add PostgreSQL/Supabase schema, row-level security policies, and
  invitation-based membership setup.
- [x] Add a per-computer shared configuration format that contains only the
  public project URL, publishable/anon key, and workspace ID.
- [x] Add account sign-in and a `SharedDatabase` backend that implements the
  same tracker operations as the existing SQLite backend.
- [x] Add a one-time local-SQLite-to-shared migration utility with a duplicate
  migration guard.
- [x] Change the desktop application to select local or shared mode and to
  avoid copying a remote database as though it were a local file.
- [x] Document first-owner setup, inviting another person, migration,
  publishing, rollback, and verification.
- [ ] Create the actual Supabase project, run the SQL, and migrate the live
  data. This remains a deliberate owner action because it requires creating a
  third-party account and supplying its project-specific public details.

## Concurrency and publishing rules

Shared ledger edits are sent directly to PostgreSQL, so a second user sees new
records after refresh/restart and changes are not based on copied `.db` files.
The web page is still static GitHub Pages output; it must be regenerated and
pushed after shared-data changes. The app's existing Publish button can do
this from either configured computer, but the GitHub repository must grant
each publisher write access. If two people publish at precisely the same time,
Git will reject one push; refresh/pull and publish again.

## Explicit non-goals

This change does not expose the database publicly, store a database password
on client computers, use cloud-folder synchronisation for SQLite, or delete
the existing local database.
