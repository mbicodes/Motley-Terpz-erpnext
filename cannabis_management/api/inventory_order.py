"""Draft Sales Orders from the Inventory Dashboard's order cart.

The dashboard (Web Page "mtm-inventory-dashboard") lets a logged-in user pick
items from any item group into a cart and save them as a draft Sales Order.
A Sales Order belongs to one company, and Fresh Frozen sits in a TSBC Ranch
warehouse while the rest sit in MTM's, so a mixed cart becomes one draft per
company. Everything runs as the user: insert() applies the usual Sales Order
permissions, permlevels and validate hooks (the credit gate lets any draft
through; it only stops at submit).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

# Select fields the popup offers, with their options read from Sales Order meta
# so a new option added on the form shows up here without a code change.
POPUP_SELECT_FIELDS = (
    "custom_sales_order_type",
    "custom_mode_of_payment",
    "custom_pickup_or_dropoff",
    "custom_logistic_status",
    "order_type",
)

PAYMENT_TERMS_MODE = "Payment Terms"


@frappe.whitelist()
def get_order_form_options():
    meta = frappe.get_meta("Sales Order")
    options = {}
    for fieldname in POPUP_SELECT_FIELDS:
        df = meta.get_field(fieldname)
        options[fieldname] = {
            "label": df.label,
            "options": [o for o in (df.options or "").split("\n") if o],
            "default": df.default or "",
            "reqd": df.reqd,
        }

    # Sales Order Item rate sits at permlevel 1 (Sales Manager only), so the
    # popup's Rate column is offered only to users who could type it on the form.
    can_set_rate = frappe.new_doc("Sales Order").has_permlevel_access_to(
        "rate", df=frappe.get_meta("Sales Order Item").get_field("rate"), permission_type="write"
    )

    return {
        "can_create": bool(frappe.has_permission("Sales Order", "create")),
        "can_set_rate": bool(can_set_rate),
        "options": options,
        "payment_terms_templates": frappe.get_all(
            "Payment Terms Template", pluck="name", order_by="name"
        ),
        "today": nowdate(),
    }


@frappe.whitelist()
def search_customers(txt=""):
    txt = f"%{txt or ''}%"
    return frappe.get_list(
        "Customer",
        filters={"disabled": 0},
        or_filters={"name": ["like", txt], "customer_name": ["like", txt]},
        fields=["name", "customer_name"],
        order_by="customer_name asc",
        limit_page_length=20,
    )


@frappe.whitelist()
def search_licenses(txt=""):
    txt = f"%{txt or ''}%"
    return frappe.get_list(
        "License",
        filters={"is_active": 1},
        or_filters={"name": ["like", txt], "licence_name": ["like", txt]},
        fields=["name", "licence_name"],
        order_by="name asc",
        limit_page_length=20,
    )


@frappe.whitelist(methods=["POST"])
def create_draft_sales_orders(items, details):
    items = frappe.parse_json(items) or []
    details = frappe._dict(frappe.parse_json(details) or {})

    frappe.has_permission("Sales Order", "create", throw=True)

    if not details.customer or not frappe.db.exists("Customer", details.customer):
        frappe.throw(_("Please select a valid Customer."))
    if not details.delivery_date:
        frappe.throw(_("Please set a Delivery Date."))
    if getdate(details.delivery_date) < getdate(nowdate()):
        frappe.throw(_("Delivery Date cannot be before today."))
    if details.custom_license and not frappe.db.exists("License", details.custom_license):
        frappe.throw(_("License {0} does not exist.").format(details.custom_license))
    if not items:
        frappe.throw(_("The order has no items."))

    # Company of each line comes from its warehouse; keep the cart's order.
    by_company = {}
    for row in items:
        row = frappe._dict(row)
        qty = flt(row.qty)
        if qty <= 0:
            frappe.throw(_("Qty for {0} must be more than 0.").format(row.item_code))
        if not frappe.db.exists("Item", {"name": row.item_code, "disabled": 0}):
            frappe.throw(_("Item {0} does not exist or is disabled.").format(row.item_code))
        company = frappe.db.get_value("Warehouse", row.warehouse, "company")
        if not company:
            frappe.throw(_("Warehouse {0} for {1} does not exist.").format(row.warehouse, row.item_code))
        line = {"item_code": row.item_code, "qty": qty, "warehouse": row.warehouse}
        # Without permlevel-1 access insert() blanks this again, as on the form.
        if flt(row.rate) > 0:
            line["rate"] = flt(row.rate)
        by_company.setdefault(company, []).append(line)

    created = []
    for company, rows in by_company.items():
        so = frappe.new_doc("Sales Order")
        so.update(
            {
                "customer": details.customer,
                "company": company,
                "transaction_date": nowdate(),
                "delivery_date": details.delivery_date,
                "order_type": details.order_type or "Sales",
                "custom_sales_order_type": details.custom_sales_order_type,
                "custom_mode_of_payment": details.custom_mode_of_payment,
                "custom_pickup_or_dropoff": details.custom_pickup_or_dropoff,
                "custom_logistic_status": details.custom_logistic_status,
                "custom_license": details.custom_license,
                "custom_notes_for_logistics": details.custom_notes_for_logistics,
                "custom_planner_notes": details.custom_planner_notes,
            }
        )
        if details.custom_mode_of_payment == PAYMENT_TERMS_MODE and details.payment_terms_template:
            so.payment_terms_template = details.payment_terms_template

        warehouses = {r["warehouse"] for r in rows}
        if len(warehouses) == 1:
            so.set_warehouse = next(iter(warehouses))

        for r in rows:
            so.append("items", dict(r, delivery_date=details.delivery_date))

        # Same as ERPNext's own mappers: fill customer, price list and item
        # details (rate from the price list) before the first save.
        so.set_missing_values()
        so.calculate_taxes_and_totals()
        so.insert()

        created.append(
            {
                "name": so.name,
                "company": company,
                "items": len(so.items),
                "total_qty": so.total_qty,
            }
        )

    return created
