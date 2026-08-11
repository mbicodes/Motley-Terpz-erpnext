"""Number Card sources for the Credit & AR Control workspace.

Each is a whitelisted method returning ``{"value": …, "fieldtype": …}``, which is
what a Number Card of type **Custom** expects. No Dashboard Chart Source DocType
is needed, keeping to the four-DocType constraint.
"""

import frappe
from frappe.utils import flt

from cannabis_management.credit_and_ar import metrics, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import INACTIVE_STATUSES


@frappe.whitelist()
def total_ar_vs_cap():
	settings = utils.get_settings()
	value = flt(settings.current_total_ar)
	return {"value": value, "fieldtype": "Currency"}


@frappe.whitelist()
def ar_cap_headroom():
	settings = utils.get_settings()
	return {
		"value": flt(settings.total_ar_cap) - flt(settings.current_total_ar),
		"fieldtype": "Currency",
	}


@frappe.whitelist()
def current_dso():
	return {"value": flt(utils.get_settings().current_dso), "fieldtype": "Float"}


@frappe.whitelist()
def current_cei():
	return {"value": flt(utils.get_settings().current_cei), "fieldtype": "Percent"}


@frappe.whitelist()
def accounts_on_hold():
	return {
		"value": frappe.db.count(
			"Customer", {"custom_on_hold": 1, "disabled": 0, "custom_is_intercompany": 0}
		),
		"fieldtype": "Int",
	}


@frappe.whitelist()
def pending_md_approvals():
	"""Terms Sales Orders plus Credit Applications waiting on the MD."""
	orders = frappe.db.count(
		"Sales Order",
		{
			"docstatus": 0,
			"custom_mode_of_payment": utils.MODE_TERMS,
			"custom_approval_status": utils.APPROVAL_PENDING,
		},
	)
	applications = 0
	if frappe.db.exists("DocType", "Credit Application"):
		applications = frappe.db.count(
			"Credit Application", {"docstatus": 0, "workflow_state": "Pending MD Approval"}
		)
	return {"value": orders + applications, "fieldtype": "Int"}


@frappe.whitelist()
def freeze_status():
	"""1 while frozen, 0 otherwise — a card that should always read zero."""
	return {
		"value": int(utils.get_settings().company_freeze_active or 0),
		"fieldtype": "Int",
	}


@frappe.whitelist()
def open_ar_cases():
	return {
		"value": frappe.db.count("AR Case", {"status": ("not in", INACTIVE_STATUSES)}),
		"fieldtype": "Int",
	}


@frappe.whitelist()
def legacy_outstanding():
	return {"value": metrics._legacy_ar(), "fieldtype": "Currency"}


# ── card definitions ─────────────────────────────────────────────────────────

NUMBER_CARDS = [
	{
		"label": "Credit — Total AR (New Book)",
		"method": "cannabis_management.credit_and_ar.dashboard.total_ar_vs_cap",
		"color": "#f97316",
	},
	{
		"label": "Credit — AR Cap Headroom",
		"method": "cannabis_management.credit_and_ar.dashboard.ar_cap_headroom",
		"color": "#3b82f6",
	},
	{
		"label": "Credit — DSO",
		"method": "cannabis_management.credit_and_ar.dashboard.current_dso",
		"color": "#8b5cf6",
	},
	{
		"label": "Credit — CEI",
		"method": "cannabis_management.credit_and_ar.dashboard.current_cei",
		"color": "#14b8a6",
	},
	{
		"label": "Credit — Accounts On Hold",
		"method": "cannabis_management.credit_and_ar.dashboard.accounts_on_hold",
		"color": "#dc2626",
	},
	{
		"label": "Credit — Pending MD Approvals",
		"method": "cannabis_management.credit_and_ar.dashboard.pending_md_approvals",
		"color": "#d97706",
	},
	{
		"label": "Credit — Freeze Active",
		"method": "cannabis_management.credit_and_ar.dashboard.freeze_status",
		"color": "#dc2626",
	},
	{
		"label": "Credit — Open AR Cases",
		"method": "cannabis_management.credit_and_ar.dashboard.open_ar_cases",
		"color": "#ef4444",
	},
	{
		"label": "Credit — Legacy Outstanding",
		"method": "cannabis_management.credit_and_ar.dashboard.legacy_outstanding",
		"color": "#8b5cf6",
	},
]


def install_number_cards():
	"""Number Card autonames from `label`, so the label *is* the docname —
	the workspace references these by name."""
	for card in NUMBER_CARDS:
		if frappe.db.exists("Number Card", card["label"]):
			frappe.db.set_value(
				"Number Card", card["label"], "method", card["method"], update_modified=False
			)
			continue

		frappe.get_doc(
			{
				"doctype": "Number Card",
				"label": card["label"],
				"type": "Custom",
				"method": card["method"],
				"color": card["color"],
				"is_public": 1,
				"show_percentage_stats": 0,
				"module": "Credit and AR",
			}
		).insert(ignore_permissions=True)
