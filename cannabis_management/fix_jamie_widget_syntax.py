"""
Fix a JavaScript SyntaxError in the Jamie Custom HTML Block expense widget.

The empty-state HTML in renderExpenseTable() is a SINGLE-QUOTED JS string that
contains an onclick handler using single quotes:

    '<div ...><a href="/jamie-expense-tracker" onclick="window.location.href='/jamie-expense-tracker';return false;">...'

The inner single quotes terminate the JS string early -> SyntaxError -> the
entire expense-widget IIFE fails to parse -> loadExpenseWidget() never runs ->
the widget is stuck on dashes/loading. Escape the inner single quotes.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.fix_jamie_widget_syntax.run
"""
import frappe


# Broken (unescaped single quotes inside a single-quoted JS string literal)
BROKEN = "onclick=\"window.location.href='/jamie-expense-tracker';return false;\""
# Fixed (single quotes escaped so they don't terminate the JS string)
FIXED = "onclick=\"window.location.href=\\'/jamie-expense-tracker\\';return false;\""


def run():
    frappe.set_user("Administrator")

    block = frappe.get_doc("Custom HTML Block", "Jamie")
    script = block.script or ""

    count = script.count(BROKEN)
    if count == 0:
        print("No broken onclick found in script field — already fixed or not present.")
        return

    block.script = script.replace(BROKEN, FIXED)
    block.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"Fixed {count} broken onclick occurrence(s) in Jamie widget script.")
    print("\nDone. Run: bench clear-cache  (then hard-refresh the workspace)")
