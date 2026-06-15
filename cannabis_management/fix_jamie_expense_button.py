"""
Fix the Jamie expense widget "+ New Entry" button to use direct window navigation
so Frappe's router doesn't intercept it, and ensure the web form is published.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.fix_jamie_expense_button.run
"""
import frappe


OLD_BTN = '<a href="/jamie-expense-tracker" class="nck-btn-new">+ New Entry</a>'
NEW_BTN = '<a href="/jamie-expense-tracker" class="nck-btn-new" onclick="window.location.href=\'/jamie-expense-tracker\';return false;">+ New Entry</a>'

OLD_EMPTY = '<div class="nck-empty">No expense entries yet — <a href="/jamie-expense-tracker">submit your first entry</a></div>'
NEW_EMPTY = '<div class="nck-empty">No expense entries yet — <a href="/jamie-expense-tracker" onclick="window.location.href=\'/jamie-expense-tracker\';return false;">submit your first entry</a></div>'


def run():
    frappe.set_user("Administrator")

    # 1. Publish the web form
    if frappe.db.exists("Web Form", "jamie-expense-tracker"):
        frappe.db.set_value("Web Form", "jamie-expense-tracker", "published", 1)
        print("Published: jamie-expense-tracker web form")
    else:
        print("WARNING: Web Form jamie-expense-tracker not found")

    # 2. Update button in Custom HTML Block HTML
    block = frappe.get_doc("Custom HTML Block", "Jamie")

    html = block.html or ""
    if OLD_BTN in html:
        block.html = html.replace(OLD_BTN, NEW_BTN)
        print("Updated: + New Entry button in HTML")
    elif NEW_BTN in html:
        print("+ New Entry button already updated — skipping HTML")
    else:
        print("WARNING: + New Entry button pattern not found in HTML")

    # 3. Update "submit your first entry" link in JS renderExpenseTable
    script = block.script or ""
    if OLD_EMPTY in script:
        block.script = script.replace(OLD_EMPTY, NEW_EMPTY)
        print("Updated: 'submit your first entry' link in JS")
    else:
        print("'submit your first entry' link pattern not found (may already be updated or not present)")

    block.save(ignore_permissions=True)
    frappe.db.commit()
    print("Saved Jamie Custom HTML Block")
    print("\nDone. Run: bench clear-cache")
