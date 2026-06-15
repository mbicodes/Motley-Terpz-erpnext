"""
Fix Jamie expense web form to match working Nikki form settings:
- allow_multiple = 0  (single form, no list view, no /new suffix needed)
- login_required = 0  (Frappe still tracks owner via session user)
Also updates the JSON on disk and removes the /new from the button onclick if present.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.fix_jamie_webform.run
"""
import frappe
import json
import os


WEB_FORM_JSON = "/home/frappeuser/frappe-bench/apps/cannabis_management/cannabis_management/cannabis_management/web_form/jamie_expense_tracker/jamie_expense_tracker.json"


def run():
    frappe.set_user("Administrator")

    # 1. Fix the web form DB record
    if frappe.db.exists("Web Form", "jamie-expense-tracker"):
        frappe.db.set_value("Web Form", "jamie-expense-tracker", {
            "allow_multiple": 0,
            "login_required": 0,
            "published": 1,
        })
        print("Updated DB: allow_multiple=0, login_required=0, published=1")
    else:
        print("WARNING: Web Form jamie-expense-tracker not found in DB")

    # 2. Fix the JSON file on disk
    if os.path.exists(WEB_FORM_JSON):
        with open(WEB_FORM_JSON, "r") as f:
            data = json.load(f)
        data["allow_multiple"] = 0
        data["login_required"] = 0
        data["published"] = 1
        with open(WEB_FORM_JSON, "w") as f:
            json.dump(data, f, indent=1)
        print("Updated JSON: allow_multiple=0, login_required=0, published=1")
    else:
        print(f"WARNING: JSON file not found at {WEB_FORM_JSON}")

    # 3. Fix the button onclick to remove /new suffix
    block = frappe.get_doc("Custom HTML Block", "Jamie")
    html = block.html or ""
    script = block.script or ""

    # Remove /new from button href and onclick
    if "/jamie-expense-tracker/new" in html:
        html = html.replace("/jamie-expense-tracker/new", "/jamie-expense-tracker")
        block.html = html
        print("Fixed HTML: removed /new suffix from button")
    else:
        print("HTML button looks correct (no /new suffix found)")

    if "/jamie-expense-tracker/new" in script:
        script = script.replace("/jamie-expense-tracker/new", "/jamie-expense-tracker")
        block.script = script
        print("Fixed JS: removed /new suffix from links")
    else:
        print("JS looks correct (no /new suffix found)")

    block.save(ignore_permissions=True)
    frappe.db.commit()
    print("\nDone. Run: bench clear-cache")
