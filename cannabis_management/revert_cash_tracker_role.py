"""
Remove the 'Cash Tracker User' role from users who were given it today.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.revert_cash_tracker_role.run
"""
import frappe


USERS_TO_REVERT = [
    "nikki@motleyterpz.com",
    "matt@motleyterpz.com",
]


def run():
    frappe.set_user("Administrator")
    for email in USERS_TO_REVERT:
        if not frappe.db.exists("User", email):
            print(f"User {email} not found, skipping")
            continue
        user_doc = frappe.get_doc("User", email)
        before = [r.role for r in user_doc.roles]
        user_doc.roles = [r for r in user_doc.roles if r.role != "Cash Tracker User"]
        after = [r.role for r in user_doc.roles]
        if len(before) != len(after):
            user_doc.save(ignore_permissions=True)
            print(f"Removed 'Cash Tracker User' from {email}")
        else:
            print(f"{email} did not have 'Cash Tracker User', skipping")
    frappe.db.commit()
    print("Done.")
