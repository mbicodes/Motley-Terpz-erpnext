import frappe

from cannabis_management.mt_dispatch.slack import client

NOT_LINKED = "Your Slack account isn't linked to an ERP user."


def slack_id_for(user):
	if not user or user in ("Administrator", "Guest"):
		return None
	row = frappe.db.get_value("User", user, ["custom_slack_user_id", "email", "enabled"], as_dict=True)
	if not row or not row.enabled:
		return None
	if row.custom_slack_user_id:
		return row.custom_slack_user_id

	slack_id = client.lookup_by_email(row.email or user)
	if slack_id:
		_remember(user, slack_id)
	return slack_id


def erp_user_for(slack_id):
	if not slack_id:
		return None
	user = frappe.db.get_value("User", {"custom_slack_user_id": slack_id, "enabled": 1}, "name")
	if user:
		return user

	info = client.user_info(slack_id) or {}
	email = ((info.get("profile") or {}).get("email") or "").strip().lower()
	if not email:
		return None
	user = frappe.db.get_value("User", {"email": email, "enabled": 1}, "name")
	if user:
		_remember(user, slack_id)
	return user


def _remember(user, slack_id):
	frappe.db.set_value("User", user, "custom_slack_user_id", slack_id, update_modified=False)


def mention(user):
	slack_id = slack_id_for(user)
	if slack_id:
		return f"<@{slack_id}>"
	return frappe.db.get_value("User", user, "full_name") or user


def full_name(user):
	return frappe.db.get_value("User", user, "full_name") or user
