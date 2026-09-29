"""The rules that decide whether a step may happen.

Each gate is a function taking (so, cfg, payload) and raising GateError with a
message written for whoever clicked the button -- not for a log. The same
functions run behind the ERP buttons, the Slack buttons and the document hooks,
so there is exactly one definition of each rule.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings

MANIFEST_DIGITS = 10


class GateError(frappe.ValidationError):
	"""A rule said no. The message is shown to the user as-is."""


class StaleAction(GateError):
	"""The order moved on before this click landed."""


# ── helpers ──────────────────────────────────────────────────────────────────


def linked_sales_orders(dn):
	"""Sales Orders a Delivery Note draws from, via its item rows."""
	return {row.against_sales_order for row in (dn.items or []) if row.get("against_sales_order")}


def delivery_notes_for(so_name, docstatus=None):
	filters = {"against_sales_order": so_name, "docstatus": ["<", 2]}
	if docstatus is not None:
		filters["docstatus"] = docstatus
	return frappe.get_all(
		"Delivery Note Item", filters=filters, pluck="parent", distinct=True
	)


def draft_delivery_note(so_name):
	"""The one draft Delivery Note for this order, or None."""
	names = delivery_notes_for(so_name, docstatus=0)
	return names[0] if names else None


def tags_with_stock(item_code, warehouse, limit=100):
	"""Metric Tags holding stock of an item in a warehouse.

	Not a Stock Ledger query. `muid` is not an inventory dimension on this site
	-- the only dimensions are Brand and Batch, and there is no muid column on
	Stock Ledger Entry at all. Per-tag quantity is a maintained field on the
	Metric Tag record itself, so that is what both the picker and G3 read.

	Consequence worth knowing: this is only as accurate as whatever keeps
	Metric Tag.current_qty in step with the ledger.
	"""
	return frappe.get_all(
		"Metric Tag",
		filters={
			"item_code": item_code,
			"warehouse": warehouse,
			"current_qty": [">", 0],
			"status": ["!=", "Empty"],
		},
		fields=["name as muid", "tag_code", "current_qty as qty"],
		order_by="current_qty desc",
		limit=limit,
	)


def tag_qty(muid):
	return flt(frappe.db.get_value("Metric Tag", muid, "current_qty"))


# ── G0 .. G5 ─────────────────────────────────────────────────────────────────


def ready_to_start(so, cfg, payload=None):
	"""G0 -- the order is allowed onto the flow at all.

	A Terms order waits for credit. Cash On Delivery does not: the money is
	collected later and G5 is what holds it back.
	"""
	if not cfg:
		raise GateError(_("{0} is not set up for dispatch.").format(so.company))

	if so.get("custom_mode_of_payment") == stages.TERMS:
		status = so.get("custom_approval_status") or ""
		if status not in stages.APPROVAL_CLEAR:
			raise GateError(
				_("This is a Payment Terms order and credit approval is {0}.").format(
					status or _("not yet requested")
				)
			)


def conversions_complete(so, cfg, payload=None):
	"""G1 -- nothing half-finished is left behind.

	A draft Conversion Entry blocks the order even when conversions were never
	flagged: a draft means someone started one and walked away.
	"""
	drafts = frappe.get_all(
		"Conversion Entry",
		filters={"sales_order": so.name, "docstatus": 0},
		pluck="name",
	)
	if drafts:
		raise GateError(
			_("Conversion Entry {0} is still a draft. Submit or delete it first.").format(
				", ".join(drafts[:3])
			)
		)

	if not so.get("custom_conversion_required"):
		return

	submitted = frappe.db.count("Conversion Entry", {"sales_order": so.name, "docstatus": 1})
	if not submitted:
		raise GateError(_("This order needs a conversion, and none has been submitted yet."))


def one_delivery_note(so, cfg, payload=None):
	"""G2 -- never a second Delivery Note for the same order."""
	existing = delivery_notes_for(so.name)
	if existing:
		raise GateError(
			_("Delivery Note {0} already covers this order.").format(existing[0])
		)


def tags_set(so, cfg, payload=None):
	"""G3 -- every line names a Metric Tag that actually holds the quantity.

	Checks the chosen tags before the Delivery Note is built, not after. G3
	guards `create_delivery_note`, and guards run before the effect, so at that
	moment there is no note to read -- only the picks in the payload, keyed by
	Sales Order Item name. Falling back to the draft note covers the gates
	being re-run later, e.g. from the ERP form.
	"""
	if not cfg or not cfg.require_muid_on_dn:
		return

	picks = (payload or {}).get("muid")
	if picks:
		for row in so.items:
			_check_tag(picks.get(row.name), row.idx, row.item_code, row.qty)
		return

	dn_name = draft_delivery_note(so.name)
	if not dn_name:
		return

	dn = frappe.get_doc("Delivery Note", dn_name)
	for row in dn.items:
		_check_tag(row.get("tags"), row.idx, row.item_code, row.qty)


def _check_tag(muid, idx, item_code, qty):
	if not muid:
		raise GateError(_("Row #{0} ({1}): no Metric Tag chosen.").format(idx, item_code))
	available = tag_qty(muid)
	if available < flt(qty):
		raise GateError(
			_("Row #{0} ({1}): tag {2} holds {3}, the line needs {4}.").format(
				idx, item_code, muid, available, flt(qty)
			)
		)


def manifest_present(so, cfg, payload=None):
	"""G4 -- a 10-digit Metrc manifest number and the file behind it.

	Checks what is being uploaded when there is a payload, because G4 guards
	the very step that performs the upload. With no payload -- at release, or
	from the ERP form -- it reads what is already on the draft note.
	"""
	dn_name = draft_delivery_note(so.name)
	if not dn_name:
		raise GateError(_("No draft Delivery Note for this order."))

	if payload and (payload.get("manifest_number") or payload.get("file_url")):
		number = (payload.get("manifest_number") or "").strip()
		has_file = bool(payload.get("file_url"))
		where = _("this upload")
	else:
		dn = frappe.db.get_value(
			"Delivery Note", dn_name, ["custom_metrc_manifest_number", "custom_manifest"], as_dict=True
		)
		number = (dn.custom_metrc_manifest_number or "").strip()
		has_file = bool(dn.custom_manifest)
		where = dn_name

	if not number:
		raise GateError(_("The Metrc manifest number is missing on {0}.").format(where))
	if not (number.isdigit() and len(number) == MANIFEST_DIGITS):
		raise GateError(
			_("The Metrc manifest number must be {0} digits. Got {1} digit(s).").format(
				MANIFEST_DIGITS, len(number)
			)
		)
	if not has_file:
		raise GateError(_("The manifest file is missing on {0}.").format(where))


def paid(so, cfg, payload=None):
	"""G5 -- Cash On Delivery is covered before the order leaves."""
	applies, amount_paid, required, short = payment_status(so, cfg)
	if not applies:
		return
	if short:
		raise GateError(
			_("This COD order is short {0}. Paid {1} of {2}.").format(
				frappe.format_value(short, {"fieldtype": "Currency"}),
				frappe.format_value(amount_paid, {"fieldtype": "Currency"}),
				frappe.format_value(required, {"fieldtype": "Currency"}),
			)
		)


# ── Delivery Note hard blocks ────────────────────────────────────────────────
#
# These sit outside transition() on purpose. They are what stops a Delivery
# Note being made or submitted around the flow -- from the ERP form, from the
# API, from anywhere. Both only ever fire for Delivery Notes that draw on a
# Sales Order belonging to an enabled company, so standalone transfers and
# every other company on the site are untouched.


def _governed_orders(dn):
	"""(sales order name, cfg) pairs this Delivery Note is governed by."""
	governed = []
	for so_name in linked_sales_orders(dn):
		company = frappe.db.get_value("Sales Order", so_name, "company")
		cfg = get_company_settings(company)
		if cfg:
			governed.append((so_name, cfg))
	return governed


def dn_before_insert(doc, method=None):
	for so_name, _cfg in _governed_orders(doc):
		if frappe.flags.get("mt_dispatch"):
			continue
		stage = frappe.db.get_value("Sales Order", so_name, "custom_logistic_status")
		frappe.throw(
			_(
				"Delivery Notes for {0} are created from the dispatch flow, not by hand. "
				"The order is at {1}."
			).format(so_name, stage or _("no stage")),
			exc=GateError,
			title=_("Dispatch Flow"),
		)


def dn_before_submit(doc, method=None):
	if frappe.flags.get("mt_dispatch") in ("release", "release_override"):
		return
	for so_name, _cfg in _governed_orders(doc):
		frappe.throw(
			_("{0} is released by an approver, which submits this Delivery Note. Don't submit it here.").format(
				so_name
			),
			exc=GateError,
			title=_("Dispatch Flow"),
		)
