"""Create a read-only web snapshot of the local Gas / Split data.

This script intentionally exports only a static HTML page. It never copies the
SQLite database or provides any form to add, edit, or delete data online.
"""

from __future__ import annotations

from datetime import datetime
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


def page(db: Database) -> str:
    events = db.all_events()
    balances, _ = db.ledger()
    pending = sum(event["kind"] == "Trip" and event["total"] is None for event in events)
    total_costs = sum(event["total"] or 0 for event in events if event["kind"] != "Payment")
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    balance_cards = "".join(
        f'<article class="card"><span>{escape(person)}</span><strong class="{"receive" if balance > 0.005 else "owe" if balance < -0.005 else "settled"}">'
        f'{"Should receive " + money(balance) if balance > 0.005 else "Owes " + money(-balance) if balance < -0.005 else "Settled up"}'
        f"</strong></article>"
        for person, balance in balances.items()
    )
    rows = []
    for event in events:
        people = f"to {event['payee']}" if event["kind"] == "Payment" else ", ".join(event["attendees"])
        total = money(event["total"]) if event["total"] is not None else "Price pending"
        notes = f'<small>{escape(event["notes"])}</small>' if event["notes"] else ""
        rows.append(
            "<tr>"
            f"<td>{escape(event['date'])}</td><td><span class=\"tag\">{escape(event['display_type'])}</span></td>"
            f"<td>{escape(event['description'])}{notes}</td><td>{escape(event['payer'])}</td>"
            f"<td>{escape(people)}</td><td>{total}</td><td>{share_text(event)}</td>"
            "</tr>"
        )
    pending_note = f"<p class=\"notice\">{pending} fuel trip{'s' if pending != 1 else ''} have a pending gas price and are excluded from balances.</p>" if pending else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gas / Split - Read-only view</title><style>
:root {{ color-scheme: light; --ink:#12304a; --muted:#61758a; --paper:#fff; --bg:#eef3f8; --line:#dce5ee; --green:#087e6b; --red:#b7472a; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:#243447; font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif }}
header {{ background:var(--ink); color:#fff; padding:48px max(24px,calc((100vw - 1180px)/2)); }} h1 {{ margin:0; letter-spacing:.06em; font-size:clamp(28px,5vw,42px) }} header p {{ color:#bdd0df; margin:6px 0 0 }}
main {{ max-width:1180px; margin:28px auto 48px; padding:0 24px }} .eyebrow {{ color:var(--muted); margin:0 0 16px }} .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px }}
.card {{ padding:18px; background:var(--paper); border:1px solid var(--line); border-radius:12px; box-shadow:0 2px 7px #112b4310 }} .card span {{ display:block; color:var(--muted); font-weight:650; margin-bottom:5px }} .card strong {{ font-size:20px }} .receive {{ color:var(--green) }} .owe {{ color:var(--red) }} .settled {{ color:var(--muted) }}
.panel {{ margin-top:22px; background:var(--paper); border:1px solid var(--line); border-radius:12px; overflow:hidden }} .panel h2 {{ color:var(--ink); font-size:19px; padding:18px 20px; margin:0; border-bottom:1px solid var(--line) }} .notice {{ margin:16px 20px; padding:11px 13px; border-radius:8px; color:#875800; background:#fff4d6 }}
.table-wrap {{ overflow-x:auto }} table {{ width:100%; border-collapse:collapse; min-width:910px }} th {{ color:var(--muted); background:#f7fafc; text-align:left; font-size:12px; letter-spacing:.02em; padding:12px 16px }} td {{ vertical-align:top; padding:13px 16px; border-top:1px solid var(--line) }} small {{ display:block; color:var(--muted); margin-top:3px }} .tag {{ display:inline-block; padding:3px 7px; border-radius:999px; color:#20506e; background:#e0edf5; font-size:12px; font-weight:650 }} footer {{ color:var(--muted); font-size:13px; margin-top:18px }}
</style></head><body><header><h1>GAS / SPLIT</h1><p>Read-only shared-cost dashboard</p></header><main>
<p class="eyebrow">Snapshot generated {escape(now)}. This page cannot modify the tracker.</p>
<section class="cards"><article class="card"><span>Shared costs tracked</span><strong>{money(total_costs)}</strong></article><article class="card"><span>Entries</span><strong>{len(events)}</strong></article>{balance_cards}</section>
<section class="panel"><h2>Activity</h2>{pending_note}<div class="table-wrap"><table><thead><tr><th>Date</th><th>What happened</th><th>Details</th><th>Paid by / from</th><th>Shared with</th><th>Total</th><th>Each share</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
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
