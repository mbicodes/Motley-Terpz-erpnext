"""
Check and update the Nikki Server Scripts.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.check_server_scripts.run
"""
import frappe


def run():
    # Discover column names first
    cols = frappe.db.sql("SHOW COLUMNS FROM `tabServer Script`", as_dict=True)
    col_names = [c['Field'] for c in cols]
    print("Server Script columns:", col_names)

    scripts = frappe.db.get_all(
        "Server Script",
        filters={"name": ["like", "Nikki%"]},
        fields=["name", "script_type", "reference_doctype", "doctype_event", "script", "disabled"],
    )

    for s in scripts:
        print(f"\n=== {s.name} ===")
        print(f"  type={s.script_type} | doctype={s.doctype_or_filter} | event={s.dt_or_filter_event} | disabled={s.disabled}")
        print(f"  --- script ---")
        print(s.script or "(empty)")
        print("  --- end ---")
