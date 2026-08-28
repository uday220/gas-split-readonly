"""Create a read-only web snapshot of the local Gas / Split data.

This script intentionally exports only a static HTML page. It never copies the
SQLite database or provides any form to add, edit, or delete data online.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from gas_tracker import DB_PATH, Database, money


OUTPUT_DIR = Path(__file__).resolve().parent / "docs"


def share_text(event: dict) -> str:
    if event["kind"] == "Payment":
        return "-"
    if event["total"] is None:
        return "Price pending"
    values = list(event["shares"].values())
    if len(set(values)) == 1:
        return money(values[0])
    return f"{money(min(values))} - {money(max(values))}"


def audit_rows(db: Database, person: str) -> str:
    _, lines = db.ledger()
    owed_lines = [
        line
        for line in lines
        if line["kind"] != "Payment" and line["amount"] < -0.005 and line["person"] != line["payer"]
    ]
    sorted_lines = sorted(
        (line for line in owed_lines if line["person"] == person),
        key=lambda event: (event["date"], event["kind"], event["description"]),
        reverse=True,
    )
    rows = []
    for line in sorted_lines:
        amount = money(-line["amount"])
        notes = f'<small>{escape(line["notes"])}</small>' if line["notes"] else ""
        total = money(line["total"]) if line["total"] is not None else "Price pending"
        rows.append(
            "<tr>"
            f"<td>{escape(line['date'])}</td>"
            f"<td>{escape(line['kind'])}</td><td>{escape(line['description'])}{notes}</td>"
            f"<td>{escape(line['payer'])}</td><td>{total}</td><td class=\"owe\">{amount}</td>"
            "</tr>"
        )
    return ''.join(rows)


def audit_tables(db: Database) -> str:
    tables = []
    for person in db.people:
        rows = audit_rows(db, person)
        content = (
            f'<div class="owed-table-wrap"><table class="audit-table"><thead><tr>'
            f'<th>Date</th><th>Type</th><th>What was it</th><th>Paid by</th><th>Total event</th><th>Owes</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
            if rows else '<p class="owed-empty">&#10003; No outstanding expenses</p>'
        )
        tables.append(f'<section class="owed-person"><h3>{escape(person)}</h3>{content}</section>')
    return "".join(tables)


def page(db: Database) -> str:
    events = db.all_events()
    balances, _ = db.ledger()
    pending = sum(event["kind"] == "Trip" and event["total"] is None for event in events)
    total_costs = sum(event["total"] or 0 for event in events if event["kind"] != "Payment")
    people_list = db.people
    people_json = json.dumps(people_list)

    balance_cards = "".join(
        f'<article class="card"><span>{escape(person)}</span><strong class="{"receive" if balance > 0.005 else "owe" if balance < -0.005 else "settled"}">'
        f'{"Should receive " + money(balance) if balance > 0.005 else "Owes " + money(-balance) if balance < -0.005 else "Settled up"}'
        f"</strong></article>"
        for person, balance in balances.items()
    )
    owed_lines = [
        line
        for line in db.ledger()[1]
        if line["kind"] != "Payment" and line["amount"] < -0.005 and line["person"] != line["payer"]
    ]
    person_owed: dict[str, dict[str, object]] = {}
    for line in owed_lines:
        person = line["person"]
        amount = -line["amount"]
        existing = person_owed.get(person)
        if existing is None or line["date"] > existing["latest_date"]:
            person_owed[person] = {
                "total": amount if existing is None else existing["total"] + amount,
                "latest_date": line["date"],
                "latest_line": line,
            }
        else:
            person_owed[person]["total"] += amount
    owed_cards = "".join(
        f'<article class="card"><span>{escape(person)}</span><strong class="owe">Owes {money(data["total"])}</strong><small>Latest owed expense: {escape(data["latest_line"]["date"])} {escape(data["latest_line"]["kind"])} paid by {escape(data["latest_line"]["payer"])}</small></article>'
        for person, data in sorted(person_owed.items(), key=lambda item: item[0])
    )
    rows = []
    for event in events:
        event_people = f"to {event['payee']}" if event["kind"] == "Payment" else ", ".join(event["attendees"])
        total = money(event["total"]) if event["total"] is not None else "Price pending"
        notes = f'<small>{escape(event["notes"])}</small>' if event["notes"] else ""
        rows.append(
            "<tr>"
            f"<td>{escape(event['date'])}</td><td><span class=\"tag\">{escape(event['display_type'])}</span></td>"
            f"<td>{escape(event['description'])}{notes}</td><td>{escape(event['payer'])}</td>"
            f"<td>{escape(event_people)}</td><td>{total}</td><td>{share_text(event)}</td>"
            "</tr>"
        )
    pending_note = f"<p class=\"notice\">{pending} fuel trip{'s' if pending != 1 else ''} have a pending gas price and are excluded from balances.</p>" if pending else ""
    request_people = "".join(f'<label class="check"><input type="checkbox" name="request-attendees" value="{escape(person)}" checked> <span>{escape(person)}</span></label>' for person in people_list)
    payer_options = "".join(f'<option value="{escape(person)}">{escape(person)}</option>' for person in people_list)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gas / Split - Read-only view</title><style>
:root {{ color-scheme: dark; --ink:#e8f2ff; --muted:#97a9bf; --paper:#0f1a2b; --paper-2:#132236; --bg:#07111d; --line:#23334a; --green:#3de0ad; --red:#ff8b72; --gold:#f0c15d; --blue:#62a8ff; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:radial-gradient(circle at top, #0e1c31 0%, #07111d 52%), var(--bg); color:#e7eef8; font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif }}
header {{ background:linear-gradient(135deg, #13263d 0%, #0f1a2b 55%, #09101a 100%); color:#fff; padding:48px max(24px,calc((100vw - 1180px)/2)); border-bottom:1px solid #1f3147; box-shadow:0 18px 45px #00000045 }} h1 {{ margin:0; letter-spacing:.08em; font-size:clamp(28px,5vw,42px) }} header p {{ color:#9fb0c8; margin:6px 0 0 }}
main {{ max-width:1180px; margin:28px auto 48px; padding:0 24px }} .eyebrow {{ color:var(--muted); margin:0 0 16px }} .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px }}
.card {{ padding:18px; background:var(--paper); border:1px solid var(--line); border-radius:16px; box-shadow:0 16px 32px #00000030 }} .card span {{ display:block; color:var(--muted); font-weight:650; margin-bottom:5px }} .card strong {{ font-size:20px }} .receive {{ color:var(--green) }} .owe {{ color:var(--red) }} .settled {{ color:var(--muted) }}
.panel {{ margin-top:22px; background:var(--paper); border:1px solid var(--line); border-radius:16px; overflow:hidden; box-shadow:0 16px 32px #00000028 }} .panel h2 {{ color:var(--ink); font-size:19px; padding:18px 20px; margin:0; border-bottom:1px solid var(--line); background:var(--paper-2) }} .notice {{ margin:16px 20px; padding:11px 13px; border-radius:10px; color:#f4d086; background:#2b2110; border:1px solid #5b4820 }}
.table-wrap {{ overflow-x:auto }} table {{ width:100%; border-collapse:collapse; min-width:760px }} th {{ color:var(--muted); background:#101c2d; text-align:left; font-size:12px; letter-spacing:.02em; padding:11px 14px; border-bottom:1px solid var(--line) }} td {{ vertical-align:top; padding:11px 14px; border-top:1px solid var(--line) }} small {{ display:block; color:var(--muted); margin-top:3px }} .tag {{ display:inline-block; padding:3px 7px; border-radius:999px; color:#b9d8ff; background:#1a2d45; font-size:12px; font-weight:650; border:1px solid #29405c }} .audit-table {{ width:100%; border-collapse:collapse; min-width:760px }} .audit-table th {{ color:var(--muted); background:#101c2d; text-align:left; font-size:12px; letter-spacing:.02em; padding:11px 14px; border-bottom:1px solid var(--line) }} .audit-table td {{ vertical-align:top; padding:11px 14px; border-top:1px solid var(--line) }} .owed-person {{ border-top:1px solid var(--line) }} .owed-person h3 {{ margin:0; padding:15px 20px 9px; color:var(--ink); font-size:17px }} .owed-table-wrap {{ overflow-x:auto; margin:0 20px 14px; border:1px solid var(--line) }} .owed-empty {{ margin:0 20px 15px; padding:10px 12px; color:var(--muted); background:#101c2d; border:1px solid var(--line); font-size:13px; font-weight:650 }} .audit-amount.receive {{ color:var(--green) }} .audit-amount.owe {{ color:var(--red) }} .audit-amount.settled {{ color:var(--muted) }}
.request-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px 14px; margin:0 20px 20px }} .field {{ display:flex; flex-direction:column; gap:6px }} .field label {{ color:var(--muted); font-size:13px; font-weight:650 }} .field input, .field select, .field textarea {{ width:100%; border:1px solid var(--line); border-radius:10px; background:#0c1725; color:#fff; padding:11px 12px; font:inherit }} .field textarea {{ min-height:92px; resize:vertical }} .field.full {{ grid-column:1 / -1 }} .people-box {{ border:1px solid var(--line); border-radius:12px; background:#0c1725; padding:12px }} .people-box .legend {{ color:var(--muted); font-size:13px; font-weight:650; margin-bottom:10px }} .people-box .summary {{ margin:10px 0 0; color:var(--green); font-size:13px; font-weight:650 }} .checks {{ display:flex; flex-wrap:wrap; gap:10px 16px }} .check {{ display:inline-flex; align-items:center; gap:8px; color:#fff; padding:7px 10px; border-radius:999px; background:#13263b; border:1px solid #29405c }} .check input {{ accent-color: var(--blue) }} .request-actions {{ display:flex; gap:10px; padding:0 20px 20px }} .request-actions button {{ border:0; border-radius:999px; padding:12px 16px; font:inherit; font-weight:700; color:#fff; background:linear-gradient(135deg, var(--blue), #2f67b8); box-shadow:0 8px 20px #00000030; cursor:pointer }} .request-actions button.secondary {{ background:#22344c }} .hint {{ margin:0 20px 14px; color:var(--muted) }} footer {{ color:var(--muted); font-size:13px; margin-top:18px }}
</style></head><body><header><h1>GAS / SPLIT</h1><p>Read-only shared-cost dashboard</p></header><main>
<p class="eyebrow">Snapshot generated from the current database contents. This page cannot modify the tracker.</p>
<section class="cards"><article class="card"><span>Shared costs tracked</span><strong>{money(total_costs)}</strong></article><article class="card"><span>Entries</span><strong>{len(events)}</strong></article>{balance_cards}</section>
<section class="panel"><h2>Activity</h2>{pending_note}<div class="table-wrap"><table><thead><tr><th>Date</th><th>What happened</th><th>Details</th><th>Paid by / from</th><th>Shared with</th><th>Total</th><th>Each share</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="panel"><h2>Owed costs</h2><p class="hint">Only active owed shares are shown here. Payments and settled transfers are excluded.</p>{audit_tables(db)}</section>
<footer>Published as a static snapshot. Data changes only when the desktop app is updated and this site is regenerated.</footer></main></body></html>"""


def main() -> None:
    db = Database(DB_PATH)
    if db.event_count() == 0:
        raise SystemExit("No tracker data found. Open the desktop app once before publishing a snapshot.")
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(page(db), encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    db.conn.close()
    print(f"Read-only site created: {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
