"""
Debug jamie-expense-tracker web form 404 issue.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.debug_jamie_webform.run
"""
import frappe

def run():
    frappe.set_user("jamie@motleyterpz.com")
    
    # 1. Check if web form exists and is published
    wf = frappe.get_doc("Web Form", "jamie-expense-tracker")
    print(f"  Web Form: {wf.name}, published={wf.published}, doc_type={wf.doc_type}")
    
    # 2. Check if doctype exists
    exists = frappe.db.exists("DocType", "Jamie Expense Entry")
    print(f"  DocType exists: {exists}")
    
    # 3. Check Jamie's permissions
    can_create = frappe.has_permission("Jamie Expense Entry", "create")
    can_read   = frappe.has_permission("Jamie Expense Entry", "read")
    print(f"  Jamie permissions: create={can_create}, read={can_read}")
    
    # 4. Simulate /jamie-expense-tracker/new request
    try:
        from frappe.website.doctype.web_form.web_form import WebForm
        wf_obj = frappe.get_doc("Web Form", "jamie-expense-tracker")
        ctx = frappe._dict()
        ctx.path = "jamie-expense-tracker/new"
        frappe.local.path = "jamie-expense-tracker/new"
        frappe.form_dict.is_new = True  # simulate /new URL
        wf_obj.get_context(ctx)
        print(f"  Context built OK: {list(ctx.keys())[:5]}")
    except frappe.exceptions.Redirect:
        print(f"  Redirects to: {frappe.local.response.get('location', '?')}")
    except Exception as e:
        import traceback
        print(f"  Context build ERROR: {type(e).__name__}: {e}")
        print(f"  Traceback:\n{traceback.format_exc()[:2000]}")
