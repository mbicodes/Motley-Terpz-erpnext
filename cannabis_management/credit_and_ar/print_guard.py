"""Server-side print blocking for unapproved Terms Sales Orders.

Hiding the Print menu client-side is cosmetic — the print and PDF endpoints are
whitelisted and reachable directly. These wrappers are registered in
``hooks.py > override_whitelisted_methods`` and sit in front of every route that
can render a document:

* ``frappe.www.printview.get_html_and_style``   — the print preview
* ``frappe.utils.print_format.download_pdf``    — Download PDF
* ``frappe.utils.weasyprint.download_pdf``      — Print Designer formats
* ``frappe.core.doctype.communication.email.make`` — emailing an attached format

Each delegates to the original once the check passes, so behaviour for every
other DocType is untouched.
"""

import json

import frappe
from frappe import _
from frappe.core.doctype.communication.email import make as _original_make
from frappe.utils.print_format import download_pdf as _original_download_pdf
from frappe.utils.weasyprint import download_pdf as _original_weasyprint_pdf
from frappe.www.printview import get_html_and_style as _original_get_html_and_style

BLOCK_MESSAGE = "Printing is blocked — this Terms order is awaiting Managing Director approval."


def _is_blocked(doctype: str | None, name: str | None) -> bool:
	if doctype != "Sales Order" or not name:
		return False
	return bool(frappe.db.get_value("Sales Order", name, "custom_print_blocked"))


def _guard(doctype: str | None, name: str | None):
	if not _is_blocked(doctype, name):
		return

	frappe.throw(
		_(
			"{0}<br><br>Ask the Managing Director or Ops Manager to approve the order, "
			"or re-type it as COD."
		).format(_(BLOCK_MESSAGE)),
		frappe.PermissionError,
		title=_("Print Blocked"),
	)


def _resolve_doc_arg(doc, name):
	"""printview passes either a doctype string plus name, or a serialised doc."""
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
	# Only block when a rendered copy of the order would actually be attached —
	# a plain note against the Sales Order is still allowed.
	if print_html or print_format:
		_guard(doctype, name)

	return _original_make(
		doctype=doctype, name=name, print_html=print_html, print_format=print_format, **kwargs
	)
