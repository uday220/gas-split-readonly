"""Supabase-backed shared storage for Gas & Cost Splitter.

This module deliberately uses only Python's standard HTTP library.  It stores
the public Supabase project URL/key and a workspace ID in a local config file,
but never stores the PostgreSQL password or another person's credentials.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from copy import copy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openpyxl import Workbook


DEFAULT_PEOPLE = ["Abdul", "Uday", "Gurpreet"]
DEFAULT_DRIVERS = {"Uday": 8.2, "Gurpreet": 7.9}


class SharedDatabaseError(ValueError):
    """A clear error returned by the hosted shared database."""


def round_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def split_cents(total: float, attendees: list[str], payer: str) -> dict[str, float]:
    if not attendees:
        raise ValueError("At least one person must share an event.")
    cents = int(Decimal(str(round_money(total))) * 100)
    base, extra = divmod(cents, len(attendees))
    order = [person for person in attendees if person != payer] + ([payer] if payer in attendees else [])
    shares = {person: base for person in attendees}
    for person in order[:extra]:
        shares[person] += 1
    return {person: value / 100 for person, value in shares.items()}


def money(value: float) -> str:
    return f"${value:,.2f}"


def config_path(directory: Path) -> Path:
    return directory / "shared_config.json"


def load_config(path: Path) -> dict[str, str]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SharedDatabaseError(
            f"Shared mode needs {path.name}. Follow SHARED_DATABASE_SETUP.md first."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SharedDatabaseError(f"{path.name} is not valid JSON: {exc.msg}") from exc
    required = ("supabase_url", "supabase_anon_key", "workspace_id")
    missing = [key for key in required if not str(config.get(key, "")).strip()]
    if missing:
        raise SharedDatabaseError(f"{path.name} is missing: {', '.join(missing)}.")
    url = str(config["supabase_url"]).rstrip("/")
    if not url.startswith("https://"):
        raise SharedDatabaseError("The Supabase URL must start with https://.")
    return {key: str(config[key]).strip() for key in required}


def save_config(path: Path, config: dict[str, str]) -> None:
    safe = {
        "supabase_url": config["supabase_url"].rstrip("/"),
        "supabase_anon_key": config["supabase_anon_key"],
        "workspace_id": config["workspace_id"],
    }
    path.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")


class SharedDatabase:
    """Tracker storage in a Supabase workspace, scoped by Row Level Security."""

    is_remote = True

    def __init__(self, config: dict[str, str], email: str, password: str):
        self._configure(config)
        self._login(email, password)
        if self.workspace_id:
            self._seed_settings()

    def _configure(self, config: dict[str, str]) -> None:
        self.url = str(config.get("supabase_url", "")).rstrip("/")
        self.anon_key = str(config.get("supabase_anon_key", ""))
        self.workspace_id = str(config.get("workspace_id", ""))
        if not self.url.startswith("https://") or not self.anon_key:
            raise SharedDatabaseError("Shared configuration needs an HTTPS Supabase URL and an anon key.")
        self.access_token = ""
        self.refresh_token = ""

    @classmethod
    def from_config(cls, path: Path, email: str, password: str) -> "SharedDatabase":
        return cls(load_config(path), email, password)

    @classmethod
    def register(cls, config: dict[str, str], email: str, password: str) -> "SharedDatabase":
        """Create an account for setup, without requiring a workspace first."""
        instance = cls.__new__(cls)
        instance._configure(config)
        instance.sign_up(email, password)
        return instance

    def _auth_request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._raw_request(
            method,
            path,
            payload,
            {"apikey": self.anon_key, "Content-Type": "application/json"},
        )

    def _login(self, email: str, password: str) -> None:
        result = self._auth_request(
            "POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password}
        )
        self._set_session(result)

    def sign_up(self, email: str, password: str) -> None:
        """Create an account. The project can require email confirmation."""
        result = self._auth_request("POST", "/auth/v1/signup", {"email": email.strip(), "password": password})
        if result.get("access_token"):
            self._set_session(result)
            return
        raise SharedDatabaseError(
            "Account created. Confirm its email address if required, then run setup again and choose sign in."
        )

    def _set_session(self, result: dict[str, Any]) -> None:
        self.access_token = str(result.get("access_token") or "")
        self.refresh_token = str(result.get("refresh_token") or "")
        if not self.access_token:
            message = result.get("msg") or result.get("message") or "Sign-in did not return an access token."
            raise SharedDatabaseError(str(message))

    def _refresh(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            result = self._auth_request(
                "POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.refresh_token}
            )
            self._set_session(result)
            return True
        except SharedDatabaseError:
            return False

    def _raw_request(
        self, method: str, path: str, payload: dict[str, Any] | list[dict[str, Any]] | None,
        headers: dict[str, str],
    ) -> dict[str, Any] | list[Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.url + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=25) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
                message = detail.get("message") or detail.get("msg") or detail.get("hint") or raw
            except json.JSONDecodeError:
                message = raw or exc.reason
            raise SharedDatabaseError(f"Shared database request failed ({exc.code}): {message}") from exc
        except URLError as exc:
            raise SharedDatabaseError(f"Cannot reach the shared database: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SharedDatabaseError("Shared database returned invalid JSON.") from exc

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        extra_headers: dict[str, str] | None = None, retry: bool = True,
    ) -> dict[str, Any] | list[Any]:
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            return self._raw_request(method, path, payload, headers)
        except SharedDatabaseError as exc:
            if retry and "(401)" in str(exc) and self._refresh():
                return self._request(method, path, payload, extra_headers, retry=False)
            raise

    def _workspace(self) -> str:
        if not self.workspace_id:
            raise SharedDatabaseError("This computer has not joined a shared workspace yet.")
        return self.workspace_id

    def _table_path(self, table: str, params: dict[str, str] | None = None) -> str:
        query = urlencode(params or {}, safe=".,()*")
        return f"/rest/v1/{table}" + (f"?{query}" if query else "")

    def _rows(self, table: str, order: str = "id.asc") -> list[dict[str, Any]]:
        params = {"workspace_id": f"eq.{self._workspace()}", "select": "*", "order": order}
        result = self._request("GET", self._table_path(table, params))
        return list(result) if isinstance(result, list) else []

    def _insert(
        self, table: str, values: dict[str, Any], *, on_conflict: str | None = None,
        resolution: str = "ignore-duplicates",
    ) -> list[dict[str, Any]]:
        values = {"workspace_id": self._workspace(), **values}
        params = {"select": "*"}
        if on_conflict:
            params["on_conflict"] = on_conflict
        headers = {"Prefer": "return=representation" + (f",resolution={resolution}" if on_conflict else "")}
        result = self._request("POST", self._table_path(table, params), values, headers)
        return list(result) if isinstance(result, list) else []

    def _update(self, table: str, record_id: int, values: dict[str, Any]) -> None:
        params = {"id": f"eq.{record_id}", "workspace_id": f"eq.{self._workspace()}"}
        self._request("PATCH", self._table_path(table, params), values, {"Prefer": "return=minimal"})

    def _delete(self, table: str, record_id: int) -> None:
        params = {"id": f"eq.{record_id}", "workspace_id": f"eq.{self._workspace()}"}
        self._request("DELETE", self._table_path(table, params), None, {"Prefer": "return=minimal"})

    def _rpc(self, name: str, values: dict[str, Any]) -> Any:
        return self._request("POST", f"/rest/v1/rpc/{name}", values, {"Prefer": "return=representation"})

    def _seed_settings(self) -> None:
        if self.get_setting("people") is None:
            self.set_setting("people", json.dumps(DEFAULT_PEOPLE))
        if self.get_setting("drivers") is None:
            self.set_setting("drivers", json.dumps(DEFAULT_DRIVERS))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        params = {
            "workspace_id": f"eq.{self._workspace()}", "key": f"eq.{key}", "select": "value", "limit": "1",
        }
        result = self._request("GET", self._table_path("gas_settings", params))
        return str(result[0]["value"]) if isinstance(result, list) and result else default

    def set_setting(self, key: str, value: str) -> None:
        self._insert(
            "gas_settings", {"key": key, "value": value}, on_conflict="workspace_id,key",
            resolution="merge-duplicates",
        )

    @property
    def people(self) -> list[str]:
        return json.loads(self.get_setting("people", "[]") or "[]")

    @property
    def drivers(self) -> dict[str, float]:
        return {name: float(rate) for name, rate in json.loads(self.get_setting("drivers", "{}") or "{}").items()}

    def event_count(self) -> int:
        return sum(len(self._rows(table)) for table in ("gas_trips", "gas_expenses", "gas_payments"))

    def pending_trip_count(self) -> int:
        params = {
            "workspace_id": f"eq.{self._workspace()}", "price_cents": "is.null", "select": "id",
        }
        result = self._request("GET", self._table_path("gas_trips", params))
        return len(result) if isinstance(result, list) else 0

    def add_trip(self, event_date: str, driver: str, kms: float, price_cents: float | None,
                 attendees: list[str], notes: str = "", fuel_efficiency: float | None = None) -> None:
        efficiency = self.drivers.get(driver) if fuel_efficiency is None else fuel_efficiency
        if efficiency is None:
            raise ValueError(f"No fuel efficiency is set for {driver}.")
        self._insert("gas_trips", {
            "event_date": event_date, "driver": driver, "kms": kms, "price_cents": price_cents,
            "fuel_efficiency": efficiency, "attendees": attendees, "notes": notes.strip(),
        })

    def update_trip(self, event_id: int, event_date: str, driver: str, kms: float, price_cents: float | None,
                    fuel_efficiency: float, attendees: list[str], notes: str = "") -> None:
        self._update("gas_trips", event_id, {
            "event_date": event_date, "driver": driver, "kms": kms, "price_cents": price_cents,
            "fuel_efficiency": fuel_efficiency, "attendees": attendees, "notes": notes.strip(),
        })

    def update_pending_trip_prices(self, price_cents: float) -> int:
        params = {"workspace_id": f"eq.{self._workspace()}", "price_cents": "is.null"}
        result = self._request(
            "PATCH", self._table_path("gas_trips", params), {"price_cents": price_cents},
            {"Prefer": "return=representation"},
        )
        return len(result) if isinstance(result, list) else 0

    def add_expense(self, event_date: str, category: str, description: str, amount: float, payer: str,
                    attendees: list[str], notes: str = "") -> None:
        self._insert("gas_expenses", {
            "event_date": event_date, "category": category.strip(), "description": description.strip(),
            "amount": round_money(amount), "payer": payer, "attendees": attendees, "notes": notes.strip(),
        })

    def update_expense(self, event_id: int, event_date: str, category: str, description: str, amount: float,
                       payer: str, attendees: list[str], notes: str = "") -> None:
        self._update("gas_expenses", event_id, {
            "event_date": event_date, "category": category.strip(), "description": description.strip(),
            "amount": round_money(amount), "payer": payer, "attendees": attendees, "notes": notes.strip(),
        })

    def add_payment(self, event_date: str, payer: str, payee: str, amount: float, notes: str = "") -> None:
        self._insert("gas_payments", {
            "event_date": event_date, "payer": payer, "payee": payee,
            "amount": round_money(amount), "notes": notes.strip(),
        })

    def update_payment(self, event_id: int, event_date: str, payer: str, payee: str, amount: float,
                       notes: str = "") -> None:
        self._update("gas_payments", event_id, {
            "event_date": event_date, "payer": payer, "payee": payee,
            "amount": round_money(amount), "notes": notes.strip(),
        })

    def delete_event(self, kind: str, event_id: int) -> None:
        table = {"Trip": "gas_trips", "Expense": "gas_expenses", "Payment": "gas_payments"}.get(kind)
        if not table:
            raise ValueError("Unknown event type.")
        self._delete(table, event_id)

    def add_expense_request(self, request_token: str, event_date: str, category: str, description: str,
                            amount: float, payer: str, attendees: list[str], notes: str = "", source: str = "") -> bool:
        rows = self._insert("gas_expense_requests", {
            "request_token": request_token, "event_date": event_date, "category": category.strip(),
            "description": description.strip(), "amount": round_money(amount), "payer": payer,
            "attendees": attendees, "notes": notes.strip(), "source": source.strip(),
        }, on_conflict="workspace_id,request_token")
        return bool(rows)

    def add_payment_request(self, request_token: str, event_date: str, payer: str, payee: str, amount: float,
                            notes: str = "", source: str = "") -> bool:
        rows = self._insert("gas_payment_requests", {
            "request_token": request_token, "event_date": event_date, "payer": payer, "payee": payee,
            "amount": round_money(amount), "notes": notes.strip(), "source": source.strip(),
        }, on_conflict="workspace_id,request_token")
        return bool(rows)

    @staticmethod
    def _attendees(row: dict[str, Any]) -> list[str]:
        value = row.get("attendees", [])
        return json.loads(value) if isinstance(value, str) else list(value or [])

    def expense_requests(self) -> list[dict[str, Any]]:
        return [{
            "kind": "Expense", "id": int(row["id"]), "request_token": row["request_token"],
            "created_at": row["created_at"], "event_date": row["event_date"], "category": row["category"],
            "description": row["description"], "amount": round_money(float(row["amount"])), "payer": row["payer"],
            "attendees": self._attendees(row), "notes": row.get("notes", ""), "source": row.get("source", ""),
        } for row in self._rows("gas_expense_requests", "created_at.desc,id.desc")]

    def payment_requests(self) -> list[dict[str, Any]]:
        return [{
            "kind": "Payment", "id": int(row["id"]), "request_token": row["request_token"],
            "created_at": row["created_at"], "event_date": row["event_date"], "payer": row["payer"],
            "payee": row["payee"], "amount": round_money(float(row["amount"])),
            "notes": row.get("notes", ""), "source": row.get("source", ""),
        } for row in self._rows("gas_payment_requests", "created_at.desc,id.desc")]

    def request_count(self) -> int:
        return len(self.expense_requests()) + len(self.payment_requests())

    def import_expense_request(self, payload: dict[str, Any], source: str = "") -> bool:
        token = str(payload.get("request_id") or payload.get("request_token") or "")
        if not token:
            token = json.dumps({key: payload.get(key, "") for key in ("event_date", "category", "description", "amount", "payer", "attendees", "notes")}, sort_keys=True)
        attendees = payload.get("attendees")
        if not isinstance(attendees, list) or not attendees:
            raise ValueError("Request file must include at least one attendee.")
        amount = float(payload["amount"])
        if amount <= 0 or payload.get("payer") not in self.people or any(person not in self.people for person in attendees):
            raise ValueError("Request must use saved people and have a positive amount.")
        description = str(payload.get("description", "")).strip()
        if not description:
            raise ValueError("Request needs a description.")
        return self.add_expense_request(token, str(payload["event_date"]), str(payload.get("category", "Other") or "Other"), description, amount, str(payload["payer"]), attendees, str(payload.get("notes", "")), source)

    def import_payment_request(self, payload: dict[str, Any], source: str = "") -> bool:
        token = str(payload.get("request_id") or payload.get("request_token") or "")
        if not token:
            token = json.dumps({key: payload.get(key, "") for key in ("event_date", "payer", "payee", "amount", "notes")}, sort_keys=True)
        payer, payee, amount = str(payload.get("payer", "")), str(payload.get("payee", "")), float(payload["amount"])
        if amount <= 0 or payer not in self.people or payee not in self.people or payer == payee:
            raise ValueError("Payment requests must use two saved people and a positive amount.")
        return self.add_payment_request(token, str(payload["event_date"]), payer, payee, amount, str(payload.get("notes", "")), source)

    def import_request(self, payload: dict[str, Any], source: str = "") -> bool:
        if str(payload.get("request_kind") or payload.get("kind") or "expense").lower() == "payment":
            return self.import_payment_request(payload, source)
        return self.import_expense_request(payload, source)

    def approve_expense_request(self, request_id: int) -> bool:
        return bool(self._rpc("gas_approve_expense_request", {"p_request_id": request_id}))

    def delete_expense_request(self, request_id: int) -> None:
        self._delete("gas_expense_requests", request_id)

    def approve_payment_request(self, request_id: int) -> bool:
        return bool(self._rpc("gas_approve_payment_request", {"p_request_id": request_id}))

    def delete_payment_request(self, request_id: int) -> None:
        self._delete("gas_payment_requests", request_id)

    def import_original_workbook_once(self, *_args: Any, **_kwargs: Any) -> tuple[bool, str]:
        return False, "Shared mode does not auto-import a spreadsheet. Use migrate_to_shared.py once."

    def all_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in self._rows("gas_trips"):
            rate = float(row["fuel_efficiency"] if row["fuel_efficiency"] is not None else self.drivers.get(row["driver"], 0))
            kms = float(row["kms"])
            price_cents = None if row["price_cents"] is None else float(row["price_cents"])
            total = None if price_cents is None else round_money(kms * rate * price_cents / 10000)
            attendees = self._attendees(row)
            shares = {} if total is None else split_cents(total, attendees, row["driver"])
            values = list(shares.values())
            events.append({
                "id": int(row["id"]), "kind": "Trip", "display_type": "Fuel trip" if total is not None else "Fuel trip - price pending",
                "date": row["event_date"], "description": f"{kms:g} km driven by {row['driver']}", "payer": row["driver"],
                "attendees": attendees, "total": total, "shares": shares, "share": values[0] if len(set(values)) == 1 else None,
                "notes": row.get("notes", ""), "price_cents": price_cents, "fuel_efficiency": rate, "kms": kms,
                "detail": f"{kms:g} km x {rate:g} L/100 km x {price_cents:g} cents/L" if total is not None else f"{kms:g} km at {rate:g} L/100 km; gas price not entered yet",
            })
        for row in self._rows("gas_expenses"):
            attendees, total = self._attendees(row), round_money(float(row["amount"]))
            shares = split_cents(total, attendees, row["payer"])
            values = list(shares.values())
            events.append({
                "id": int(row["id"]), "kind": "Expense", "display_type": f"Shared {row['category'].lower()} expense",
                "category": row["category"], "date": row["event_date"], "description": f"{row['category']}: {row['description']}",
                "raw_description": row["description"], "payer": row["payer"], "attendees": attendees, "total": total,
                "shares": shares, "share": values[0] if len(set(values)) == 1 else None, "notes": row.get("notes", ""), "detail": row["category"],
            })
        for row in self._rows("gas_payments"):
            events.append({
                "id": int(row["id"]), "kind": "Payment", "display_type": "Payment sent", "date": row["event_date"],
                "description": f"{row['payer']} paid {row['payee']}", "payer": row["payer"], "payee": row["payee"], "attendees": [],
                "total": round_money(float(row["amount"])), "shares": {}, "share": None, "notes": row.get("notes", ""), "detail": "Settlement payment",
            })
        return sorted(events, key=lambda event: (event["date"], event["kind"], event["id"]), reverse=True)

    def ledger(self) -> tuple[dict[str, float], list[dict[str, Any]]]:
        balances_cents = defaultdict(int, {person: 0 for person in self.people})
        lines: list[dict[str, Any]] = []
        for event in self.all_events():
            if event["total"] is None:
                continue
            total_cents = int(Decimal(str(event["total"])) * 100)
            if event["kind"] == "Payment":
                balances_cents[event["payer"]] += total_cents
                balances_cents[event["payee"]] -= total_cents
                lines.extend(({**event, "person": event["payer"], "amount": event["total"], "reason": f"Paid {event['payee']}"}, {**event, "person": event["payee"], "amount": -event["total"], "reason": f"Received from {event['payer']}"}))
                continue
            for attendee in event["attendees"]:
                balances_cents[attendee] -= int(Decimal(str(event["shares"][attendee])) * 100)
                lines.append({**event, "person": attendee, "amount": -event["shares"][attendee], "reason": "Share of cost"})
            balances_cents[event["payer"]] += total_cents
            lines.append({**event, "person": event["payer"], "amount": event["total"], "reason": "Paid upfront"})
        return {person: cents / 100 for person, cents in balances_cents.items()}, lines

    def settlements(self) -> list[tuple[str, str, float]]:
        balances, _ = self.ledger()
        debtors = [[name, -amount] for name, amount in balances.items() if amount < -0.005]
        creditors = [[name, amount] for name, amount in balances.items() if amount > 0.005]
        suggestions = []
        while debtors and creditors:
            debtor, debt = debtors[0]
            creditor, credit = creditors[0]
            paid = min(debt, credit)
            suggestions.append((debtor, creditor, paid))
            debtors[0][1] -= paid
            creditors[0][1] -= paid
            if debtors[0][1] < 0.005:
                debtors.pop(0)
            if creditors and creditors[0][1] < 0.005:
                creditors.pop(0)
        return suggestions

    def export_csv(self, destination: Path) -> int:
        balances, lines = self.ledger()
        with destination.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Date", "Type", "Description", "Person", "Ledger amount", "Reason", "Paid by", "Total event cost", "Notes"])
            for line in sorted(lines, key=lambda row: (row["date"], row["id"]), reverse=True):
                writer.writerow([line["date"], line["kind"], line["description"], line["person"], round(line["amount"], 2), line["reason"], line["payer"], round(line["total"], 2), line["notes"]])
            writer.writerow([])
            writer.writerow(["Balance check", "", "", "", round(sum(balances.values()), 2)])
        return len(lines)

    def export_xlsx(self, destination: Path) -> int:
        balances, lines = self.ledger()
        workbook = Workbook()
        ledger_sheet = workbook.active
        ledger_sheet.title = "Ledger"
        headers = ["Date", "Type", "Description", "Person", "Ledger amount", "Reason", "Paid by", "Total event cost", "Notes"]
        ledger_sheet.append(headers)
        for cell in ledger_sheet[1]:
            font = copy(cell.font); font.bold = True; cell.font = font
        for line in sorted(lines, key=lambda row: (row["date"], row["id"]), reverse=True):
            ledger_sheet.append([line["date"], line["kind"], line["description"], line["person"], round(line["amount"], 2), line["reason"], line["payer"], round(line["total"], 2), line["notes"]])
        balance_sheet = workbook.create_sheet("Balances")
        balance_sheet.append(["Person", "Balance"])
        for cell in balance_sheet[1]:
            font = copy(cell.font); font.bold = True; cell.font = font
        for person, balance in balances.items():
            balance_sheet.append([person, round(balance, 2)])
        balance_sheet.append([]); balance_sheet.append(["Balance check", round(sum(balances.values()), 2)])
        workbook.save(destination)
        return len(lines)

    def close(self) -> None:
        """Match the local backend API; HTTPS requests have no open connection."""

    # Setup-only RPCs. They intentionally do not expose any privileged database secret.
    def create_workspace(self, name: str) -> str:
        result = self._rpc("gas_create_workspace", {"p_name": name.strip()})
        if not isinstance(result, str) or not result:
            raise SharedDatabaseError("Workspace creation did not return an ID.")
        self.workspace_id = result
        self._seed_settings()
        return result

    def create_invite(self) -> str:
        result = self._rpc("gas_create_invite", {"p_workspace_id": self._workspace()})
        if not isinstance(result, str) or not result:
            raise SharedDatabaseError("Invite creation did not return a code.")
        return result

    def accept_invite(self, code: str) -> str:
        result = self._rpc("gas_accept_invite", {"p_code": code.strip()})
        if not isinstance(result, str) or not result:
            raise SharedDatabaseError("Invite did not return a workspace ID.")
        self.workspace_id = result
        self._seed_settings()
        return result

    def import_snapshot(self, snapshot: dict[str, Any], marker: str) -> dict[str, Any]:
        """Atomically import the retained local ledger once (owner only)."""
        result = self._rpc("gas_import_legacy_snapshot", {
            "p_workspace_id": self._workspace(), "p_snapshot": snapshot, "p_marker": marker,
        })
        if not isinstance(result, dict):
            raise SharedDatabaseError("Migration did not return its import summary.")
        return result
