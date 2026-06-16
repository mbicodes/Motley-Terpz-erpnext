"""
Set up role-based access to Nikki's cash-ledger / expense widget data.

Creates the "Nikki Ledger" role and ensures Nikki can hold it. Because Nikki is
governed by the "Sales Manager" Role Profile (Frappe re-applies a profiled user's
roles from the profile on every save, wiping ad-hoc roles), the role must be added
to her Role Profile rather than assigned directly.

To grant access to anyone else later:
  - User WITHOUT a role profile  -> just assign them the "Nikki Ledger" role.
  - User WITH a role profile     -> add "Nikki Ledger" to that profile.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.setup_nikki_ledger_role.run
"""
import frappe

ROLE = "Nikki Ledger"
NIKKI_USER = "nikki@motleyterpz.com"


def run():
    frappe.set_user("Administrator")

    # 1. Create the role if missing
    if not frappe.db.exists("Role", ROLE):
        role = frappe.new_doc("Role")
        role.role_name = ROLE
        role.desk_access = 1
        role.insert(ignore_permissions=True)
        print(f"Created role: {ROLE}")
    else:
        print(f"Role already exists: {ROLE}")

    # 2. Figure out how Nikki gets her roles
    profile = frappe.db.get_value("User", NIKKI_USER, "role_profile_name")

    if profile:
        # Add the role to her Role Profile so it survives User saves
        rp = frappe.get_doc("Role Profile", profile)
        if ROLE not in [r.role for r in rp.roles]:
            rp.append("roles", {"role": ROLE})
            rp.save(ignore_permissions=True)
            print(f"Added '{ROLE}' to Role Profile '{profile}'")
        else:
            print(f"Role Profile '{profile}' already has '{ROLE}'")
        # Re-sync Nikki's user so she picks up the profile change
        u = frappe.get_doc("User", NIKKI_USER)
        u.save(ignore_permissions=True)
    else:
        # No profile -> assign directly
        u = frappe.get_doc("User", NIKKI_USER)
        if ROLE not in [r.role for r in u.roles]:
            u.append("roles", {"role": ROLE})
            u.save(ignore_permissions=True)
            print(f"Assigned '{ROLE}' directly to {NIKKI_USER}")

    frappe.db.commit()
    has = ROLE in frappe.get_roles(NIKKI_USER)
    print(f"Verify: {NIKKI_USER} has '{ROLE}' -> {has}")
