"""
Co-Pack Cost & Quote Calculator.

Given a co-packing job's inputs — client raw-material cost, packaging components,
run size, and labor hours — computes total cost, per-unit cost and a suggested
margin-adjusted customer quote, using ERPNext item costs for packaging and a
Finance-maintained rate table (Co-Pack Settings) for labor / overhead / margin.
Optionally spins up a draft ERPNext BOM if the job is won.
"""

import json
import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_settings():
    s = frappe.get_single("Co-Pack Settings")
    return {
        "labor_rate_per_hour": flt(s.labor_rate_per_hour) or 25.0,
        "overhead_pct": flt(s.overhead_pct) or 15.0,
        "default_margin_pct": flt(s.default_margin_pct) or 30.0,
        "packaging_price_source": s.packaging_price_source or "Valuation Rate",
    }


def _item_unit_cost(item_code, source):
    if not item_code:
        return 0.0
    if source == "Last Purchase Rate":
        rate = frappe.db.get_value("Item", item_code, "last_purchase_rate")
        if flt(rate) > 0:
            return flt(rate)
    # default / fallback: valuation rate from stock, then last purchase rate
    val = frappe.db.get_value("Item", item_code, "valuation_rate")
    if flt(val) > 0:
        return flt(val)
    return flt(frappe.db.get_value("Item", item_code, "last_purchase_rate"))


@frappe.whitelist()
def calculate(payload):
    """payload (JSON): {
        raw_material_cost, run_qty, labor_hours,
        labor_rate_per_hour?, overhead_pct?, margin_pct?,
        packaging: [{item_code, qty_per_unit}]
    }  →  cost breakdown + suggested quote.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)

    s = get_settings()
    run_qty = flt(payload.get("run_qty"))
    if run_qty <= 0:
        frappe.throw(_("Run quantity must be greater than zero."))

    labor_rate = flt(payload.get("labor_rate_per_hour")) or s["labor_rate_per_hour"]
    overhead_pct = payload.get("overhead_pct")
    overhead_pct = flt(overhead_pct) if overhead_pct not in (None, "") else s["overhead_pct"]
    margin_pct = payload.get("margin_pct")
    margin_pct = flt(margin_pct) if margin_pct not in (None, "") else s["default_margin_pct"]

    raw_material_cost = flt(payload.get("raw_material_cost"))
    labor_hours = flt(payload.get("labor_hours"))
    labor_cost = labor_hours * labor_rate

    # Packaging — per-unit item costs from ERPNext × qty per unit × run size
    packaging_lines = []
    packaging_total = 0.0
    for row in (payload.get("packaging") or []):
        item_code = row.get("item_code")
        qty_per_unit = flt(row.get("qty_per_unit")) or 1.0
        unit_cost = _item_unit_cost(item_code, s["packaging_price_source"])
        line_total = unit_cost * qty_per_unit * run_qty
        packaging_total += line_total
        packaging_lines.append({
            "item_code": item_code,
            "item_name": frappe.db.get_value("Item", item_code, "item_name") if item_code else "",
            "qty_per_unit": qty_per_unit,
            "unit_cost": round(unit_cost, 4),
            "line_total": round(line_total, 2),
        })

    subtotal = raw_material_cost + labor_cost + packaging_total
    overhead_cost = subtotal * overhead_pct / 100.0
    total_cost = subtotal + overhead_cost
    cost_per_unit = total_cost / run_qty if run_qty else 0.0

    # Suggested quote: price so that margin_pct of the price is profit.
    if margin_pct >= 100:
        margin_pct = 99.0
    suggested_price_per_unit = cost_per_unit / (1 - margin_pct / 100.0) if margin_pct < 100 else cost_per_unit
    suggested_quote_total = suggested_price_per_unit * run_qty

    return {
        "inputs": {
            "run_qty": run_qty, "labor_hours": labor_hours, "labor_rate_per_hour": labor_rate,
            "overhead_pct": overhead_pct, "margin_pct": margin_pct,
            "raw_material_cost": raw_material_cost,
        },
        "breakdown": {
            "raw_material_cost": round(raw_material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "packaging_total": round(packaging_total, 2),
            "overhead_cost": round(overhead_cost, 2),
            "packaging_lines": packaging_lines,
        },
        "total_cost": round(total_cost, 2),
        "cost_per_unit": round(cost_per_unit, 4),
        "suggested_price_per_unit": round(suggested_price_per_unit, 4),
        "suggested_quote_total": round(suggested_quote_total, 2),
        "margin_per_unit": round(suggested_price_per_unit - cost_per_unit, 4),
    }


@frappe.whitelist()
def create_draft_bom(payload):
    """Create a draft ERPNext BOM for the finished-good item from the packaging
    components (used when a co-pack job is won). Returns the BOM name."""
    if isinstance(payload, str):
        payload = json.loads(payload)

    fg_item = payload.get("fg_item")
    if not fg_item or not frappe.db.exists("Item", fg_item):
        frappe.throw(_("Select a valid finished-good Item to build the BOM for."))

    company = payload.get("company") or frappe.defaults.get_global_default("company")
    if not company:
        company = frappe.db.get_value("Company", {}, "name")

    bom = frappe.new_doc("BOM")
    bom.item = fg_item
    bom.company = company
    bom.quantity = flt(payload.get("run_qty")) or 1
    bom.is_active = 1
    bom.is_default = 0
    for row in (payload.get("packaging") or []):
        if row.get("item_code"):
            bom.append("items", {
                "item_code": row["item_code"],
                "qty": flt(row.get("qty_per_unit")) or 1,
            })
    bom.insert()
    frappe.msgprint(
        _("Draft BOM {0} created for {1}.").format(
            f'<a href="/app/bom/{bom.name}">{bom.name}</a>', fg_item),
        indicator="green", title=_("BOM Created"))
    return {"bom": bom.name}
