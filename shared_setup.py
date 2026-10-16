"""Create or join a shared Gas & Cost Splitter workspace.

Run this script from a copy of the project after the Supabase SQL schema has
been installed. It writes only shared_config.json (public URL/key/workspace
ID), never a database password or a user's sign-in password.
"""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from shared_database import SharedDatabase, SharedDatabaseError, config_path, load_config, save_config


BASE_DIR = Path(__file__).resolve().parent


def ask_project_details() -> dict[str, str]:
    url = input("Supabase project URL (https://...supabase.co): ").strip()
    anon_key = getpass.getpass("Supabase publishable/anon key (input hidden): ").strip()
    return {"supabase_url": url, "supabase_anon_key": anon_key, "workspace_id": ""}


def sign_in(project: dict[str, str], allow_sign_up: bool) -> SharedDatabase:
    email = input("Your shared-workspace email: ").strip()
    password = getpass.getpass("Password (input hidden): ")
    if allow_sign_up and input("Create a new Supabase account with these credentials? [y/N]: ").strip().lower() in {"y", "yes"}:
        return SharedDatabase.register(project, email, password)
    return SharedDatabase(project, email, password)


def create_owner_workspace() -> None:
    target = config_path(BASE_DIR)
    if target.exists():
        raise SharedDatabaseError(f"{target.name} already exists. Use `shared_setup.py invite` or remove it only if intentional.")
    project = ask_project_details()
    client = sign_in(project, allow_sign_up=True)
    name = input("Name for this shared ledger [Gas / Split]: ").strip() or "Gas / Split"
    project["workspace_id"] = client.create_workspace(name)
    save_config(target, project)
    print(f"Created shared workspace. Public configuration saved to: {target}")
    print("Next: run `python shared_setup.py invite` to create a one-time invite for another person.")


def create_invite() -> None:
    target = config_path(BASE_DIR)
    config = load_config(target)
    client = sign_in(config, allow_sign_up=False)
    print("One-time invite code (expires in 7 days):")
    print(client.create_invite())
    print("Send the code plus the project URL and anon key to the person privately. They run `python shared_setup.py join`.")


def join_workspace() -> None:
    target = config_path(BASE_DIR)
    if target.exists():
        raise SharedDatabaseError(f"{target.name} already exists. This computer is already configured; do not overwrite it.")
    project = ask_project_details()
    client = sign_in(project, allow_sign_up=True)
    invite = getpass.getpass("One-time invite code (input hidden): ").strip()
    project["workspace_id"] = client.accept_invite(invite)
    save_config(target, project)
    print(f"Joined the shared workspace. Public configuration saved to: {target}")
    print("Start the desktop app normally and sign in when prompted.")


def verify() -> None:
    config = load_config(config_path(BASE_DIR))
    client = sign_in(config, allow_sign_up=False)
    balances, _ = client.ledger()
    print(f"Connected. Entries: {client.event_count()}; people: {', '.join(client.people)}")
    print("Balances:")
    for person, balance in balances.items():
        print(f"  {person}: {balance:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up or verify the shared Gas & Cost Splitter workspace.")
    parser.add_argument("action", choices=("owner", "invite", "join", "verify"))
    action = parser.parse_args().action
    try:
        {"owner": create_owner_workspace, "invite": create_invite, "join": join_workspace, "verify": verify}[action]()
    except SharedDatabaseError as exc:
        raise SystemExit(f"Setup stopped: {exc}") from exc


if __name__ == "__main__":
    main()
