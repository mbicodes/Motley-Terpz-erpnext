"""
Tolling / Processing Cost Calculator.

Given input material weight, a yield assumption and a tolling rate (plus optional
labor / overhead), computes expected output weight, total tolling cost, and cost
per output unit — the per-batch tolling economics reps need before quoting a
processing job. Can pre-fill the yield from historical Lab Tolling Data.
"""

import json
import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_avg_yield():
    """Average yield % from historical Lab Tolling Data, if that doctype exists.
    Used only to pre-fill the form; safe to ignore."""
    if not frappe.db.exists("DocType", "Lab Tolling Data"):
        return None
    for field in ("yield_", "yield_percent", "yield_pct", "yield"):
        if frappe.db.has_column("Lab Tolling Data", field):
            avg = frappe.db.sql(
                f"SELECT AVG(`{field}`) FROM `tabLab Tolling Data` WHERE `{field}` > 0"
            )
            if avg and avg[0][0]:
                return round(flt(avg[0][0]), 2)
    return None


@frappe.whitelist()
def calculate(payload):
    """payload (JSON): {
        input_lbs, yield_pct,
        rate_basis ('input'|'output'), rate_per_lb,
        labor_hours?, labor_rate_per_hour?, overhead_pct?, margin_pct?
    } → per-batch tolling cost breakdown.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)

    input_lbs = flt(payload.get("input_lbs"))
    yield_pct = flt(payload.get("yield_pct"))
    if input_lbs <= 0:
        frappe.throw(_("Input material weight must be greater than zero."))
    if yield_pct <= 0:
        frappe.throw(_("Expected yield % must be greater than zero."))

    output_lbs = input_lbs * yield_pct / 100.0

    rate_basis = payload.get("rate_basis") or "input"
    rate_per_lb = flt(payload.get("rate_per_lb"))
    if rate_basis == "output":
        tolling_fee = rate_per_lb * output_lbs
    else:
        tolling_fee = rate_per_lb * input_lbs

    labor_cost = flt(payload.get("labor_hours")) * flt(payload.get("labor_rate_per_hour"))
    base = tolling_fee + labor_cost
    overhead_pct = flt(payload.get("overhead_pct"))
    overhead_cost = base * overhead_pct / 100.0
    total_cost = base + overhead_cost

    cost_per_output_lb = total_cost / output_lbs if output_lbs else 0.0

    margin_pct = flt(payload.get("margin_pct"))
    if margin_pct >= 100:
        margin_pct = 99.0
    suggested_price_per_output_lb = (
        cost_per_output_lb / (1 - margin_pct / 100.0) if margin_pct else cost_per_output_lb
    )

    return {
        "output_lbs": round(output_lbs, 3),
        "breakdown": {
            "tolling_fee": round(tolling_fee, 2),
            "labor_cost": round(labor_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "rate_basis": rate_basis,
            "rate_per_lb": rate_per_lb,
        },
        "total_cost": round(total_cost, 2),
        "cost_per_output_lb": round(cost_per_output_lb, 4),
        "suggested_price_per_output_lb": round(suggested_price_per_output_lb, 4),
        "suggested_quote_total": round(suggested_price_per_output_lb * output_lbs, 2),
    }
