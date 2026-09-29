# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
#
# Tabular/exportable twin of the CFO Dashboard's Income Statement tab: FTM vs
# selected Period vs trailing Full Year, each with Actual / PY / vs PY / Budget / vs Budget.

import frappe
from frappe import _

from cannabis_management.api.cfo_dashboard import (
	Ledger,
	build_context,
	get_default_fiscal_year,
	income_statement_matrix,
	resolve_currency,
)

SUBS = (("actual", _("Actual")), ("py", _("PY")), ("vs_py", _("vs PY")), ("budget", _("Budget")), ("vs_budget", _("vs Budget")))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	by_range = filters.filter_based_on == "Date Range"
	ctx = build_context(
		filters.company,
		None if by_range else (filters.fiscal_year or get_default_fiscal_year(filters.company)),
		filters.from_date if by_range else None,
		filters.to_date if by_range else None,
		filters.project,
		filters.cost_center,
	)
	matrix = income_statement_matrix(Ledger(ctx), ctx)
	currency, _symbol = resolve_currency(ctx.companies)

	columns = [{"label": _("Particulars"), "fieldname": "label", "fieldtype": "Data", "width": 220}]
	for g in matrix["groups"]:
		for key, label in SUBS:
			columns.append(
				{"label": f"{g['label']} {label}", "fieldname": f"{g['key']}_{key}", "fieldtype": "Currency", "options": "currency", "width": 120}
			)

	columns.append({"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1})

	data = []
	for r in matrix["rows"]:
		row = {"label": r["label"], "bold": r["bold"], "currency": currency}
		for g in matrix["groups"]:
			for key, _label in SUBS:
				row[f"{g['key']}_{key}"] = r[g["key"]][key]
		data.append(row)

	message = " | ".join(f"{g['label']}: {g['period']}" for g in matrix["groups"])
	return columns, data, message
