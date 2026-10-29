import frappe

from cannabis_management.time_clock.api import TIME_CLOCK_ROLE

EXCLUDED_USERS = ("Guest", "Administrator")


def ensure_role():
	if frappe.db.exists("Role", TIME_CLOCK_ROLE):
		print(f"Role '{TIME_CLOCK_ROLE}' already exists.")
		return

	role = frappe.new_doc("Role")
	role.role_name = TIME_CLOCK_ROLE
	role.desk_access = 1
	role.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Created role '{TIME_CLOCK_ROLE}'.")


def grant_all_enabled_users():
	ensure_role()

	users = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"name": ["not in", EXCLUDED_USERS],
			"user_type": ["in", ["System User", "Website User"]],
		},
		pluck="name",
	)

	granted = []
	for user in users:
		doc = frappe.get_doc("User", user)
		if TIME_CLOCK_ROLE in [r.role for r in doc.roles]:
			continue
		doc.append("roles", {"role": TIME_CLOCK_ROLE})
		doc.save(ignore_permissions=True)
		granted.append(user)

	frappe.db.commit()
	print(f"Granted '{TIME_CLOCK_ROLE}' to {len(granted)} user(s): {', '.join(granted) or 'none'}")
	return granted


def grant(user):
	ensure_role()

	doc = frappe.get_doc("User", user)
	if TIME_CLOCK_ROLE in [r.role for r in doc.roles]:
		print(f"{user} already has '{TIME_CLOCK_ROLE}'.")
		return

	doc.append("roles", {"role": TIME_CLOCK_ROLE})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"Granted '{TIME_CLOCK_ROLE}' to {user}.")
