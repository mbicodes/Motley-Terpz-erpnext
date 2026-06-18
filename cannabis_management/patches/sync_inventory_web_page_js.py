"""
Sync the inventory dashboard Web Pages stored in the database with the
current JS file from the cannabis_management page module.

Targets any Web Page whose route contains 'inventory-dashboard', including:
  - inventory-dashboard-2 (source)
  - inventory-dashboard-mtm (MTM clone)
  - inventory-dashboard  (or any live alias)

For MTM pages the Fresh Frozen default warehouse is locked to
"Master Touch Manufacturing Toll - MTM" instead of "Hemet TSBC - TSBC".
"""

import os

import frappe

MTM_WH = "Master Touch Manufacturing Toll - MTM"

_JS_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "cannabis_management",
    "page",
    "inventory_sales_dashboard",
    "inventory_sales_dashboard.js",
)

_HTML_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "cannabis_management",
    "page",
    "inventory_sales_dashboard",
    "inventory_sales_dashboard.html",
)


def _patch_js_for_mtm(js):
    """Override Fresh Frozen default warehouse for MTM pages."""
    return js.replace(
        "'Fresh Frozen':  'Hemet TSBC - TSBC'",
        f"'Fresh Frozen':  '{MTM_WH}'",
    ).replace(
        "'Fresh Frozen': 'Hemet TSBC - TSBC'",
        f"'Fresh Frozen': '{MTM_WH}'",
    )


def execute():
    with open(_JS_FILE) as f:
        base_js = f.read()

    html = ""
    if os.path.exists(_HTML_FILE):
        with open(_HTML_FILE) as f:
            html = f.read()

    pages = frappe.get_all(
        "Web Page",
        filters={"route": ["like", "%inventory-dashboard%"]},
        fields=["name", "route", "title"],
    )

    if not pages:
        print("  No inventory-dashboard Web Pages found — nothing to update.")
        return

    for p in pages:
        is_mtm = "mtm" in (p.route or "").lower() or "mtm" in (p.title or "").lower()
        js = _patch_js_for_mtm(base_js) if is_mtm else base_js

        doc = frappe.get_doc("Web Page", p.name)
        doc.javascript = js
        if html:
            if is_mtm:
                patched_html = html.replace(
                    "Inventory Dashboard", "MTM Inventory Dashboard"
                ).replace(
                    "Motley Terpz stock visibility for invoicing and sales",
                    "Master Touch Manufacturing stock visibility for invoicing and sales",
                )
                doc.main_section_html = patched_html
            else:
                doc.main_section_html = html
        doc.save(ignore_permissions=True)
        print(f"  OK – updated Web Page: {p.name} (route: /{p.route})")

    frappe.db.commit()
    print("\nDone.")
