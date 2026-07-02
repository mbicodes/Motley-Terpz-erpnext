"""
Quote → Sales Order conversion.

One click turns an APPROVED, submitted Quotation into a draft ERPNext Sales
Order, keeping the CRM Deal ↔ Quotation ↔ Sales Order chain linked:
  • The real ERPNext Customer is resolved even when the quote was raised against
    a CRM Deal (quotation_to = "CRM Deal", where party_name is the deal name).
  • The Sales Order carries the crm_deal link (custom field) and each SO line
    links back to the source Quotation (prevdoc_docname), so ERPNext marks the
    quotation "Ordered".
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_days


@frappe.whitelist()
def create_sales_order_from_quotation(quotation):
    q = frappe.get_doc("Quotation", quotation)

    if q.docstatus != 1:
        frappe.throw(_("Submit (and get approval for) the quotation before converting it to a Sales Order."))
    if (q.get("custom_approval_status") or "") != "Approved":
        frappe.throw(_("Only an <b>Approved</b> quotation can be converted to a Sales Order."))

    customer = _resolve_erp_customer(q)
    if not customer:
        frappe.throw(_(
            "Could not resolve an ERPNext Customer for this quotation. "
            "Link the CRM Deal to a Customer (or raise the quote against a Customer) first."
        ))

    existing = _existing_sales_orders(q.name)

    delivery_date = q.get("valid_till")
    if not delivery_date or getdate(delivery_date) < getdate(nowdate()):
        delivery_date = add_days(nowdate(), 7)

    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.company = q.company
    so.currency = q.currency
    so.selling_price_list = q.get("selling_price_list")
    so.order_type = "Sales"
    so.transaction_date = nowdate()
    so.delivery_date = delivery_date
    so.crm_deal = q.get("crm_deal")
    if q.get("taxes_and_charges"):
        so.taxes_and_charges = q.taxes_and_charges

    for it in q.items:
        so.append("items", {
            "item_code": it.item_code,
            "item_name": it.item_name,
            "description": it.description,
            "uom": it.uom,
            "qty": it.qty,
            "rate": it.rate,
            "price_list_rate": it.price_list_rate,
            "discount_percentage": it.discount_percentage,
            "warehouse": it.get("warehouse") or _default_warehouse(it.item_code, q.company),
            "delivery_date": delivery_date,
            "prevdoc_docname": q.name,   # links the line back to the Quotation
        })

    so.additional_discount_percentage = flt(q.get("additional_discount_percentage"))
    if q.get("apply_discount_on"):
        so.apply_discount_on = q.apply_discount_on

    so.flags.ignore_pricing_rule = True
    so.insert()

    frappe.msgprint(
        _("Sales Order {0} created from quotation {1}.").format(
            f'<a href="/app/sales-order/{so.name}">{so.name}</a>', q.name
        ),
        title=_("Sales Order Created"),
        indicator="green",
    )
    return {"sales_order": so.name, "had_existing": bool(existing), "existing": existing}


def _resolve_erp_customer(q):
    """Resolve the real ERPNext Customer for a quotation, whether it was raised
    against a Customer directly or against a CRM Deal / Prospect."""
    if q.get("quotation_to") == "Customer" and q.get("party_name"):
        return q.party_name

    deal = q.get("crm_deal")
    if deal:
        cust = frappe.db.get_value("Customer", {"crm_deal": deal}, "name")
        if cust:
            return cust
        if frappe.db.exists("DocType", "CRM Deal") and frappe.db.has_column("CRM Deal", "erpnext_customer"):
            cust = frappe.db.get_value("CRM Deal", deal, "erpnext_customer")
            if cust:
                return cust
    return None


def _default_warehouse(item_code, company):
    """Best-effort delivery warehouse for a stock item: item default for the
    company → Stock Settings default → any enabled warehouse for the company."""
    wh = frappe.db.get_value(
        "Item Default", {"parent": item_code, "company": company}, "default_warehouse"
    )
    if wh:
        return wh
    wh = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    if wh and frappe.db.get_value("Warehouse", wh, "company") == company:
        return wh
    # Last resort: any enabled, non-group warehouse — but avoid transit/WIP ones.
    candidates = frappe.get_all(
        "Warehouse",
        filters={"company": company, "is_group": 0, "disabled": 0},
        pluck="name",
        order_by="name",
    )
    for name in candidates:
        if "transit" not in name.lower() and "wip" not in name.lower():
            return name
    return candidates[0] if candidates else None


def _existing_sales_orders(quotation_name):
    """Sales Orders already created from this quotation (linked via SO items)."""
    return frappe.db.sql_list(
        """
        SELECT DISTINCT parent FROM `tabSales Order Item`
        WHERE prevdoc_docname = %s
        """,
        quotation_name,
    )


# ── Custom field installer (idempotent) ──────────────────────────────────────

def install_quote_to_order_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    if not frappe.db.has_column("Sales Order", "crm_deal"):
        create_custom_fields({
            "Sales Order": [
                {"fieldname": "crm_deal", "fieldtype": "Data", "label": "CRM Deal",
                 "read_only": 1, "no_copy": 1, "insert_after": "customer_name",
                 "in_standard_filter": 1},
            ]
        }, ignore_validate=True)
        frappe.db.commit()
