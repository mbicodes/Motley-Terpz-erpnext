"""
Patch GROUP_DEFAULT_WAREHOUSE in inventory dashboard Web Pages to add
Primes and 0.5g O2 Vape default warehouses.

Uses targeted string replacement — only touches the GROUP_DEFAULT_WAREHOUSE
constant, never replaces the whole JS file.
"""

import frappe

MTM_WH = "Master Touch Manufacturing Toll - MTM"

OLD_GROUP_WH = "const GROUP_DEFAULT_WAREHOUSE = {\n    'Fresh Frozen': 'Hemet TSBC - TSBC'\n};"

NEW_GROUP_WH = (
    "const GROUP_DEFAULT_WAREHOUSE = {\n"
    "    'Fresh Frozen':  'Hemet TSBC - TSBC',\n"
    "    'Primes':        'Master Touch Manufacturing Toll - MTM',\n"
    "    '0.5g O2 Vape':  'Conversion - MTM',\n"
    "};"
)

NEW_GROUP_WH_MTM = (
    "const GROUP_DEFAULT_WAREHOUSE = {\n"
    "    'Fresh Frozen':  '" + MTM_WH + "',\n"
    "    'Primes':        '" + MTM_WH + "',\n"
    "    '0.5g O2 Vape':  '" + MTM_WH + "',\n"
    "};"
)

OLD_DEFAULT_WH = "const DEFAULT_WAREHOUSE = \"Nature's Lab - MT\";"
NEW_DEFAULT_WH_MTM = 'const DEFAULT_WAREHOUSE = "' + MTM_WH + '";'


def execute():
    pages = frappe.get_all(
        "Web Page",
        filters={"route": ["like", "%inventory-dashboard%"]},
        fields=["name", "route", "title"],
    )

    if not pages:
        print("  No inventory-dashboard Web Pages found — nothing to update.")
        return

    for p in pages:
        doc = frappe.get_doc("Web Page", p.name)
        js = doc.javascript or ""

        if not js:
            print(f"  SKIP {p.name} — no javascript")
            continue

        is_mtm = "mtm" in (p.route or "").lower() or "mtm" in (p.title or "").lower()

        if is_mtm:
            js = js.replace(OLD_GROUP_WH, NEW_GROUP_WH_MTM)
            js = js.replace(OLD_DEFAULT_WH, NEW_DEFAULT_WH_MTM)
        else:
            js = js.replace(OLD_GROUP_WH, NEW_GROUP_WH)

        if js == doc.javascript:
            print(f"  NO CHANGE {p.name} (string not found — already patched?)")
            continue

        doc.javascript = js
        doc.save(ignore_permissions=True)
        print(f"  OK – patched: {p.name} (/{p.route})")

    frappe.db.commit()
    print("\nDone.")
