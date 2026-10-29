import json

import frappe
from frappe import _
from frappe.utils import flt
from frappe.core.doctype.communication.email import make as _original_make
from frappe.utils.print_format import download_pdf as _original_download_pdf
from frappe.utils.weasyprint import download_pdf as _original_weasyprint_pdf
from frappe.www.printview import get_html_and_style as _original_get_html_and_style

from cannabis_management.credit_and_ar import utils

BLOCK_MESSAGE = "Printing is blocked — this Terms order is awaiting Managing Director approval."
HOLD_BLOCK_MESSAGE = "Printing is blocked — this customer's account is on {0}."
COD_BLOCK_MESSAGE = (
	"Printing is blocked — this customer is on COD and this order is on Payment Terms."
)
OVER_LINE_MESSAGE = (
	"Printing is blocked — this order is over the customer's available credit line. "
	"Only an Account Manager can print it."
)

OVER_LINE = "__over_line__"

_PRINT_BLOCKING_STATUSES = (utils.STATUS_COD, utils.STATUS_HARD_HOLD, utils.STATUS_BLOCKED)


def _is_blocked(doctype: str | None, name: str | None) -> tuple[bool, str | None]:
	if doctype != "Sales Order" or not name:
		return False, None

	so = frappe.db.get_value(
		"Sales Order",
		name,
		["docstatus", "custom_print_blocked", "custom_mode_of_payment", "customer"],
		as_dict=True,
	)
	if not so:
		return False, None

	if so.docstatus != 0:
		return False, None

	if int(so.custom_print_blocked or 0):
		return True, None

	if so.custom_mode_of_payment == utils.MODE_TERMS and so.customer and not utils.is_policy_exempt(
		so.customer
	):
		credit_status = frappe.get_cached_value("Customer", so.customer, "custom_credit_status")
		if credit_status in _PRINT_BLOCKING_STATUSES:
			return True, credit_status

	if _is_over_line(so, name):
		return True, OVER_LINE

	return False, None


def _is_over_line(so, name) -> bool:
	if not so.customer or utils.is_policy_exempt(so.customer):
		return False

	credit_status = frappe.get_cached_value("Customer", so.customer, "custom_credit_status")
	if credit_status not in utils.LINE_ENFORCED_STATUSES:
		return False

	if utils.can_override_line():
		return False

	from cannabis_management.credit_and_ar import credit_engine

	grand_total = frappe.db.get_value("Sales Order", name, "grand_total")
	available = credit_engine.get_available_line(so.customer, exclude_sales_order=name)
	return flt(grand_total) > flt(available)


def _guard(doctype: str | None, name: str | None):
	blocked, hold_status = _is_blocked(doctype, name)
	if not blocked:
		return

	if hold_status == OVER_LINE:
		frappe.throw(
			_(OVER_LINE_MESSAGE),
			frappe.PermissionError,
			title=_("Print Blocked"),
		)

	if hold_status:
		if hold_status == utils.STATUS_COD:
			frappe.throw(
				_(COD_BLOCK_MESSAGE),
				frappe.PermissionError,
				title=_("Printing Blocked"),
			)

		frappe.throw(
			_(HOLD_BLOCK_MESSAGE).format(_(hold_status)),
			frappe.PermissionError,
			title=_("Print Blocked"),
		)

	frappe.throw(
		_(
			"{0}<br><br>Ask the Managing Director or Ops Manager to approve the order, "
			"or re-type it as COD."
		).format(_(BLOCK_MESSAGE)),
		frappe.PermissionError,
		title=_("Print Blocked"),
	)


def _resolve_doc_arg(doc, name):
	if isinstance(doc, str) and name:
		return doc, name

	if isinstance(doc, str):
		try:
			parsed = json.loads(doc)
		except (ValueError, TypeError):
			return doc, name
		if isinstance(parsed, dict):
			return parsed.get("doctype"), parsed.get("name")

	if isinstance(doc, dict):
		return doc.get("doctype"), doc.get("name")

	return None, name


@frappe.whitelist()
def get_html_and_style(
	doc,
	name=None,
	print_format=None,
	no_letterhead=None,
	letterhead=None,
	trigger_print=False,
	style=None,
	settings=None,
):
	doctype, docname = _resolve_doc_arg(doc, name)
	_guard(doctype, docname)

	return _original_get_html_and_style(
		doc=doc,
		name=name,
		print_format=print_format,
		no_letterhead=no_letterhead,
		letterhead=letterhead,
		trigger_print=trigger_print,
		style=style,
		settings=settings,
	)


@frappe.whitelist(allow_guest=True)
def download_pdf(
	doctype,
	name,
	format=None,
	doc=None,
	no_letterhead=0,
	language=None,
	letterhead=None,
	pdf_generator=None,
):
	_guard(doctype, name)

	return _original_download_pdf(
		doctype=doctype,
		name=name,
		format=format,
		doc=doc,
		no_letterhead=no_letterhead,
		language=language,
		letterhead=letterhead,
		pdf_generator=pdf_generator,
	)


@frappe.whitelist()
def weasyprint_download_pdf(doctype, name, print_format, letterhead=None):
	_guard(doctype, name)
	return _original_weasyprint_pdf(
		doctype=doctype, name=name, print_format=print_format, letterhead=letterhead
	)


@frappe.whitelist()
def make(doctype=None, name=None, print_html=None, print_format=None, **kwargs):
	if print_html or print_format:
		_guard(doctype, name)

	return _original_make(
		doctype=doctype, name=name, print_html=print_html, print_format=print_format, **kwargs
	)
