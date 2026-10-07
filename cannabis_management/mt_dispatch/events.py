"""Thread notes for what happens around an order without moving its stage.

Its Sales Invoice, a Delivery Note made outside the flow, each Conversion Entry
against it, and edits to its delivery details. Each one becomes a reply in the
order's existing Slack thread (post.on_event) -- never a new top-level message.
"""

import frappe
from frappe.utils import format_date, getdate

from cannabis_management.mt_dispatch import notify
from cannabis_management.mt_dispatch.gates import _governed_orders
from cannabis_management.mt_dispatch.settings import get_company_settings


def _note(sales_order, what, **kwargs):
	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_event",
		sales_order=sales_order,
		what=what,
		actor=frappe.session.user,
		enqueue_after_commit=True,
		queue="short",
		**kwargs,
	)


# ── Sales Invoice ────────────────────────────────────────────────────────────


def _invoice_orders(si):
	if not get_company_settings(si.company):
		return []
	orders = []
	for row in si.items or []:
		if row.get("sales_order") and row.sales_order not in orders:
			orders.append(row.sales_order)
	return orders


def on_si_insert(doc, method=None):
	for so_name in _invoice_orders(doc):
		_note(so_name, "invoice_created", ref=doc.name)


def on_si_submit(doc, method=None):
	for so_name in _invoice_orders(doc):
		_note(so_name, "invoice_submitted", ref=doc.name)


def on_si_cancel(doc, method=None):
	for so_name in _invoice_orders(doc):
		_note(so_name, "invoice_cancelled", ref=doc.name)


# ── Delivery Note ────────────────────────────────────────────────────────────


def on_dn_insert(doc, method=None):
	"""A note the flow itself made is announced by that step's own reply."""
	if frappe.flags.get("mt_dispatch"):
		return
	for so_name, _cfg in _governed_orders(doc):
		_note(so_name, "dn_created", ref=doc.name)


# ── Conversion Entry ─────────────────────────────────────────────────────────


def on_ce_change(doc, method=None):
	if not doc.get("sales_order") or not frappe.db.exists("Sales Order", doc.sales_order):
		return
	if not get_company_settings(frappe.db.get_value("Sales Order", doc.sales_order, "company")):
		return
	what = "conversion_cancelled" if method == "on_cancel" else "conversion_submitted"
	_note(doc.sales_order, what, ref=doc.name)


# ── Sales Order edited after submit ──────────────────────────────────────────

WATCHED_FIELDS = (
	("delivery_date", "Delivery date"),
	("custom_pickup_or_dropoff", "Pickup or Dropoff"),
	("custom_notes_for_logistics", "Logistics note"),
)


def _shown(field, value):
	if not value:
		return ""
	if field == "delivery_date":
		return format_date(value)
	return frappe.utils.strip_html(str(value)).strip()[:300]


def on_so_change(doc, method=None):
	if not get_company_settings(doc.company):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	changes = []
	for field, label in WATCHED_FIELDS:
		old, new = before.get(field), doc.get(field)
		if field == "delivery_date":
			old, new = (getdate(old) if old else None), (getdate(new) if new else None)
		if (old or None) != (new or None):
			changes.append([label, _shown(field, old), _shown(field, new)])
	if changes:
		_note(doc.name, "so_changed", changes=changes)
