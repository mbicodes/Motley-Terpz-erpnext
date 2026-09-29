"""Move open orders onto the dispatch stages.

Only submitted orders that are still live, and only in companies with an
enabled Dispatch Company Settings record. Every order that moves gets one
stage log row with source System, so the board has a starting point in its own
audit trail. Nothing is posted to Slack from here -- threads for orders that
were already open are posted by a separate command once the channels exist.

Idempotent: an order already sitting on a new stage is left alone.
"""

import frappe

from cannabis_management.mt_dispatch import gates, install, stages
from cannabis_management.mt_dispatch.flow import _append_log
from cannabis_management.mt_dispatch.gates import GateError
from cannabis_management.mt_dispatch.settings import get_company_settings

LEGACY_TO_STAGE = {
	"": stages.RECEIVED,
	"Need to Schedule": stages.RECEIVED,
	"Scheduled": stages.RECEIVED,
	"Order Preparing": stages.PREPARING,
	"Order Prepared": stages.PREPARED,
	"Order Staged": stages.DN_READY,
	"Order Closed Out": stages.CLOSED_OUT,
}


def execute():
	install.install()

	companies = [
		row.company
		for row in frappe.get_all("Dispatch Company Settings", filters={"enabled": 1}, fields=["company"])
	]
	if not companies:
		frappe.db.commit()
		return

	orders = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "company": ["in", companies]},
		fields=["name", "company", "status", "per_delivered", "custom_logistic_status"],
	)

	moved = 0
	for row in orders:
		current = row.custom_logistic_status or ""
		if current in stages.ALL_STAGES:
			continue

		target = resolve_stage(row, current)
		if not target:
			continue

		frappe.db.set_value(
			"Sales Order", row.name, "custom_logistic_status", target, update_modified=False
		)
		so = frappe._dict(name=row.name)
		_append_log(so, current or None, target, "backfill", "System", note=None, user="Administrator")
		moved += 1

	frappe.db.commit()
	print(f"mt_dispatch: {moved} order(s) moved onto dispatch stages across {len(companies)} company(ies)")


def resolve_stage(row, current):
	"""Where one order lands. Returns None to leave it alone."""
	if row.status in ("Closed", "Cancelled"):
		return None

	if row.status == "Closed" or (row.per_delivered or 0) >= 100 or current == "Order Closed Out":
		return stages.CLOSED_OUT

	target = LEGACY_TO_STAGE.get(current)
	if not target:
		return None

	# A note already drafted means the order is further along than its old
	# label says: Prepared with a draft note is really Delivery Note Ready.
	if target == stages.PREPARED and gates.draft_delivery_note(row.name):
		target = stages.DN_READY

	# And a staged order whose manifest is already on that note is waiting to
	# be released, not waiting to be manifested.
	if target == stages.DN_READY:
		so = frappe.get_doc("Sales Order", row.name)
		cfg = get_company_settings(so.company)
		try:
			gates.manifest_present(so, cfg)
			target = stages.AWAITING_RELEASE
		except GateError:
			pass

	return target
