"""
Creates live-menu-mtm and inventory-dashboard-mtm Web Pages
cloned from live-menu-2 and inventory-dashboard-2, locked to
warehouse Master Touch Manufacturing Toll - MTM.
"""

import frappe

MTM_WH = "Master Touch Manufacturing Toll - MTM"


def _patch_live_menu_html(html):
    html = html.replace("Extracts Live Menu", "MTM Live Menu")
    return html


def _patch_live_menu_js(js):
    # Pass menu_type: 'extracts' to the backend so it filters to MTM warehouse
    old = "args: { item_group: itemGroup },"
    new = "args: { item_group: itemGroup, menu_type: 'extracts' },"
    js = js.replace(old, new)
    return js


def _patch_inv_dashboard_html(html):
    html = html.replace("Inventory Dashboard", "MTM Inventory Dashboard")
    html = html.replace(
        "Motley Terpz stock visibility for invoicing and sales",
        "Master Touch Manufacturing stock visibility for invoicing and sales",
    )
    return html


def _patch_inv_dashboard_js(js):
    # Lock default warehouse to MTM
    js = js.replace(
        "const DEFAULT_WAREHOUSE = \"Nature's Lab - MT\";",
        'const DEFAULT_WAREHOUSE = "' + MTM_WH + '";',
    )
    # Lock Fresh Frozen group default to MTM as well
    js = js.replace(
        "const GROUP_DEFAULT_WAREHOUSE = {\n    'Fresh Frozen': 'Hemet TSBC - TSBC'\n};",
        "const GROUP_DEFAULT_WAREHOUSE = {\n    'Fresh Frozen': '" + MTM_WH + "'\n};",
    )
    # Also handle any whitespace variant
    js = js.replace(
        "'Fresh Frozen': 'Hemet TSBC - TSBC'",
        "'Fresh Frozen': '" + MTM_WH + "'",
    )
    return js


def execute():
    frappe.flags.ignore_permissions = True

    pages = [
        {
            "src":   "live-menu-2",
            "name":  "live-menu-mtm",
            "title": "MTM Live Menu",
            "route": "mtm-live",
            "patch_html": _patch_live_menu_html,
            "patch_js":   _patch_live_menu_js,
        },
        {
            "src":   "inventory-dashboard-2",
            "name":  "inventory-dashboard-mtm",
            "title": "MTM Inventory Dashboard",
            "route": "mtm-inventory-dashboard",
            "patch_html": _patch_inv_dashboard_html,
            "patch_js":   _patch_inv_dashboard_js,
        },
    ]

    for p in pages:
        if not frappe.db.exists("Web Page", p["src"]):
            print(f"  SKIP – source page not found: {p['src']}")
            continue

        src = frappe.get_doc("Web Page", p["src"])

        if frappe.db.exists("Web Page", p["name"]):
            doc = frappe.get_doc("Web Page", p["name"])
        else:
            doc = frappe.new_doc("Web Page")

        doc.name              = p["name"]
        doc.title             = p["title"]
        doc.route             = p["route"]
        doc.published         = 1
        doc.content_type      = src.content_type or "HTML"
        doc.full_width        = src.full_width
        doc.show_title        = src.show_title
        doc.main_section_html = p["patch_html"](src.main_section_html or "")
        doc.javascript        = p["patch_js"](src.javascript or "")
        doc.css               = src.css or ""

        doc.save(ignore_permissions=True)
        print(f"  OK – {p['name']} (route: /{p['route']})")

    frappe.db.commit()
    print("\nDone.")
