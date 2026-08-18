"""One-time setup helpers for the Time Clock module.

Run after installing/migrating:

    bench --site <site> execute cannabis_management.time_clock.setup.ensure_role
    bench --site <site> execute cannabis_management.time_clock.setup.grant_all_enabled_users

``grant_all_enabled_users`` is opt-in on purpose. Holding "Time Clock User" is what
puts somebody on the roster, so bulk-granting is a deliberate decision rather than
something that happens quietly on migrate.
"""

import frappe

from cannabis_management.time_clock.api import TIME_CLOCK_ROLE

# Never auto-grant to these — they are not people who clock in.
EXCLUDED_USERS = ("Guest", "Administrator")


def ensure_role():
	"""Create the Time Clock User role if it does not exist."""
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
	"""Give every enabled human user the time clock role."""
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
	"""Give one user the time clock role."""
	ensure_role()

	doc = frappe.get_doc("User", user)
	if TIME_CLOCK_ROLE in [r.role for r in doc.roles]:
		print(f"{user} already has '{TIME_CLOCK_ROLE}'.")
		return

	doc.append("roles", {"role": TIME_CLOCK_ROLE})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"Granted '{TIME_CLOCK_ROLE}' to {user}.")
