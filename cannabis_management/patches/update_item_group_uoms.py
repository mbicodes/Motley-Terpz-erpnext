"""
Patch: update stock_uom, sales_uom, and purchase_uom for items by item group.

Item Group          → UOM
-----------           ---
Primes              → Gram
Subprimes           → Gram
Full Spec           → Gram
Food Grade          → Gram
DISTALLATE          → Gram
LIQUID LIVE RESIN   → Gram
Packaged goods      → Nos
Fresh Frozen Main   → LBS
Fresh Frozen - SHO  → LBS
Fresh Frozen - BHO  → LBS
"""

import frappe


GROUP_UOM_MAP = {
    "Primes":             "Gram",
    "Subprimes":          "Gram",
    "Full Spec":          "Gram",
    "Food Grade":         "Gram",
    "DISTALLATE":         "Gram",
    "LIQUID LIVE RESIN":  "Gram",
    "Packaged goods":     "Nos",
    "Fresh Frozen Main":  "LBS",
    "Fresh Frozen - SHO": "LBS",
    "Fresh Frozen - BHO": "LBS",
}


def execute():
    for item_group, uom in GROUP_UOM_MAP.items():
        items = frappe.db.get_all(
            "Item",
            filters={"item_group": item_group, "disabled": 0},
            pluck="name",
        )
        if not items:
            frappe.logger().info(f"[update_item_group_uoms] No items in group '{item_group}' — skipped")
            continue

        frappe.db.sql(
            """
            UPDATE `tabItem`
            SET stock_uom    = %(uom)s,
                sales_uom    = %(uom)s,
                purchase_uom = %(uom)s,
                modified     = NOW(),
                modified_by  = 'Administrator'
            WHERE item_group = %(group)s
              AND disabled   = 0
            """,
            {"uom": uom, "group": item_group},
        )

        frappe.logger().info(
            f"[update_item_group_uoms] '{item_group}' → {uom}  ({len(items)} item(s))"
        )
        print(f"  {item_group:<25} → {uom}  ({len(items)} items)")

    frappe.db.commit()
    print("Done — item UOMs updated.")
