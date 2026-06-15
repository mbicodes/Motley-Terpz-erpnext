import frappe

def run():
    frappe.set_user("Administrator")

    users_to_fix = []
    # Add Cash Tracker User role to any user linked to a Cash Tracker Person
    # who doesn't already have it
    ctps = frappe.db.sql(
        "SELECT name, user FROM `tabCash Tracker Person` WHERE user IS NOT NULL AND user != '' AND user != 'Administrator'",
        as_dict=True
    )

    for ctp in ctps:
        user_doc = frappe.get_doc("User", ctp.user)
        existing_roles = [r.role for r in user_doc.roles]
        if "Cash Tracker User" not in existing_roles:
            user_doc.append("roles", {"role": "Cash Tracker User"})
            user_doc.save(ignore_permissions=True)
            print(f"Added 'Cash Tracker User' role to {ctp.user} (CTP: {ctp.name})")
            users_to_fix.append(ctp.user)
        else:
            print(f"{ctp.user} already has 'Cash Tracker User' role")

    frappe.db.commit()
    if users_to_fix:
        print(f"\nDone. Updated {len(users_to_fix)} user(s): {users_to_fix}")
    else:
        print("\nNo changes needed.")
