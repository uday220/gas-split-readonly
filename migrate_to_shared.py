"""Atomically copy the existing local SQLite ledger into an empty shared workspace.

This script never edits or deletes gas_tracker.db. The hosted SQL function
performs all inserts in one transaction and rejects repeat/nonempty imports.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
from pathlib import Path
from typing import Any

from gas_tracker import DB_PATH, Database
from shared_database import SharedDatabase, SharedDatabaseError, config_path, load_config


BASE_DIR = Path(__file__).resolve().parent


def rows(db: Database, table: str) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for row in db.conn.execute(f"SELECT * FROM {table} ORDER BY id"):
        item = dict(row)
        if "attendees" in item:
            item["attendees"] = json.loads(item["attendees"])
        # The remote schema owns its own IDs and timestamps.
        item.pop("id", None)
        item.pop("created_at", None)
        snapshot.append(item)
    return snapshot


def make_snapshot(db: Database) -> dict[str, Any]:
    return {
        "people": json.dumps(db.people),
        "drivers": json.dumps(db.drivers),
        "trips": rows(db, "trips"),
        "expenses": rows(db, "expenses"),
        "payments": rows(db, "payments"),
        "expense_requests": rows(db, "expense_requests"),
        "payment_requests": rows(db, "payment_requests"),
    }


def marker_for(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sqlite_migration_" + hashlib.sha256(encoded).hexdigest()[:32]


def balances_match(local: dict[str, float], remote: dict[str, float]) -> bool:
    return local.keys() == remote.keys() and all(abs(local[key] - remote[key]) < 0.005 for key in local)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the retained local ledger to the empty shared workspace once.")
    parser.add_argument("--check", action="store_true", help="Show the pending local snapshot without sending data.")
    args = parser.parse_args()
    local = Database(DB_PATH)
    try:
        snapshot = make_snapshot(local)
        counts = {key: len(snapshot[key]) for key in ("trips", "expenses", "payments", "expense_requests", "payment_requests")}
        print("Local snapshot:", ", ".join(f"{key}={value}" for key, value in counts.items()))
        print("Local balances:", {name: round(value, 2) for name, value in local.ledger()[0].items()})
        if args.check:
            return
        confirmation = input("This copies the above data to an EMPTY shared workspace. Type MIGRATE to continue: ").strip()
        if confirmation != "MIGRATE":
            raise SystemExit("Migration cancelled; local data was not changed.")
        config = load_config(config_path(BASE_DIR))
        email = input("Workspace owner email: ").strip()
        password = getpass.getpass("Password (input hidden): ")
        remote = SharedDatabase(config, email, password)
        result = remote.import_snapshot(snapshot, marker_for(snapshot))
        remote_balances, _ = remote.ledger()
        if remote.event_count() != local.event_count() or not balances_match(local.ledger()[0], remote_balances):
            raise SharedDatabaseError(
                "The hosted import completed but verification did not match. Stop using shared mode and keep the local backup."
            )
        print("Migration verified.")
        print("Imported:", result)
        print("Shared balances:", {name: round(value, 2) for name, value in remote_balances.items()})
        print("The local gas_tracker.db was not modified. Keep it and the redesign backup.")
    finally:
        local.close()


if __name__ == "__main__":
    try:
        main()
    except SharedDatabaseError as exc:
        raise SystemExit(f"Migration stopped: {exc}") from exc
