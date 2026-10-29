import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings, is_administrator

MANIFEST_DIGITS = 10


class GateError(frappe.ValidationError):
	pass


class StaleAction(GateError):
	pass


def linked_sales_orders(dn):
	return {row.against_sales_order for row in (dn.items or []) if row.get("against_sales_order")}


def delivery_notes_for(so_name, docstatus=None):
	filters = {"against_sales_order": so_name, "docstatus": ["<", 2]}
	if docstatus is not None:
		filters["docstatus"] = docstatus
	return frappe.get_all(
		"Delivery Note Item", filters=filters, pluck="parent", distinct=True
	)


def draft_delivery_note(so_name):
	names = delivery_notes_for(so_name, docstatus=0)
	return names[0] if names else None


def conversion_targets(so_name):
	rows = frappe.db.sql(
		"""
		select cei.target_warehouse, cei.finished_good_1, cei.finished_good_2, cei.finished_good_3
		from `tabConversion Entry Item` cei
		join `tabConversion Entry` ce on ce.name = cei.parent
		where ce.sales_order = %s and ce.docstatus = 1 and ifnull(cei.target_warehouse, '') != ''
		""",
		so_name,
		as_dict=True,
	)
	targets = {}
	for r in rows:
		for item_code in (r.finished_good_1, r.finished_good_2, r.finished_good_3):
			if item_code and r.target_warehouse not in targets.setdefault(item_code, []):
				targets[item_code].append(r.target_warehouse)
	return targets


def reserved_warehouses(so_name, row_name):
	rows = frappe.db.sql(
		"""
		select warehouse, sum(reserved_qty - delivered_qty) as qty
		from `tabStock Reservation Entry`
		where docstatus = 1 and voucher_type = 'Sales Order' and voucher_no = %s
		  and voucher_detail_no = %s and status not in ('Delivered', 'Cancelled')
		group by warehouse
		order by qty desc
		""",
		(so_name, row_name),
		as_dict=True,
	)
	return {r.warehouse: flt(r.qty) for r in rows if flt(r.qty) > 0}


def delivery_warehouse(so, row, targets=None, follow_reservation=True):
	if follow_reservation and row.get("name") and so.get("name"):
		held = reserved_warehouses(so.name, row.name)
		if held:
			return next(iter(held))
	default = row.warehouse or so.set_warehouse
	need = flt(row.stock_qty) or flt(row.qty)
	if targets is None:
		targets = conversion_targets(so.name)
	for warehouse in targets.get(row.item_code, []):
		held = flt(frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": warehouse}, "actual_qty"))
		if held >= need:
			return warehouse
	return default


def ready_to_start(so, cfg, payload=None):
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
	existing = delivery_notes_for(so.name)
	if existing:
		raise GateError(
			_("Delivery Note {0} already covers this order.").format(existing[0])
		)


def manifest_present(so, cfg, payload=None):
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


def _governed_orders(dn):
	governed = []
	for so_name in linked_sales_orders(dn):
		company = frappe.db.get_value("Sales Order", so_name, "company")
		cfg = get_company_settings(company)
		if cfg:
			governed.append((so_name, cfg))
	return governed


def dn_before_insert(doc, method=None):
	if is_administrator():
		return
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
	if frappe.flags.get("mt_dispatch") in ("release", "release_override") or is_administrator():
		return
	for so_name, _cfg in _governed_orders(doc):
		frappe.throw(
			_("{0} is released by an approver, which submits this Delivery Note. Don't submit it here.").format(
				so_name
			),
			exc=GateError,
			title=_("Dispatch Flow"),
		)
