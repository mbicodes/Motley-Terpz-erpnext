# Copyright (c) 2026, alltechvirtual.com
# License: MIT

"""Export helper for the standard (erpnext) "Profit and Loss Statement" report.

Adds a whitelisted endpoint that, given the filters currently applied on the
Profit and Loss Statement and a list of accounts shown in it, runs the
standard "General Ledger" report for each account (with the exact same
date range / company / cost center / project / finance book / currency
filters) and returns a single Excel workbook with one sheet per account —
mirroring what a user would get by clicking each account row and exporting
its General Ledger, just done for every account in one go.
"""

import datetime
import json
from io import BytesIO

import frappe
import openpyxl
from frappe import _
from frappe.desk.utils import provide_binary_file
from frappe.utils import flt, getdate
from frappe.utils.xlsxutils import ILLEGAL_CHARACTERS_RE, get_excel_date_format, handle_html
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.workbook.child import INVALID_TITLE_REGEX

from erpnext.accounts.report.financial_statements import get_period_list
from erpnext.accounts.report.general_ledger.general_ledger import execute as run_general_ledger

MAX_SHEET_NAME_LENGTH = 31
INVALID_SHEET_NAME_CHARS = ["\\", "/", "*", "?", ":", "[", "]"]


@frappe.whitelist()
def export_accounts_general_ledger(filters, accounts):
	"""Return an .xlsx with one sheet per account's General Ledger entries.

	Args:
	    filters: JSON string / dict of the Profit and Loss Statement's
	        currently applied filter values (company, filter_based_on,
	        from_fiscal_year/to_fiscal_year or period_start_date/
	        period_end_date, cost_center, project, finance_book,
	        presentation_currency, include_default_book_entries).
	    accounts: JSON string / list of account names to export.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	filters = frappe._dict(filters or {})
	accounts = frappe.parse_json(accounts) if isinstance(accounts, str) else accounts

	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))

	if not accounts:
		frappe.throw(_("No accounts found to export"))

	# de-duplicate while preserving the order the report showed them in
	seen = set()
	accounts = [a for a in accounts if not (a in seen or seen.add(a))]

	# Defensive: the P&L report also emits synthetic summary rows ("Total
	# Income (Credit)", "Profit for the year", ...) with quoted, non-account
	# values in the same `.account` field. Silently drop anything that isn't
	# a real Account instead of letting the General Ledger call blow up.
	real_accounts = set(
		frappe.db.get_all("Account", filters={"name": ["in", accounts]}, pluck="name")
	)
	accounts = [a for a in accounts if a in real_accounts]

	if not accounts:
		frappe.throw(_("No accounts found to export"))

	from_date, to_date = get_pnl_date_range(filters)
	base_gl_filters = build_base_gl_filters(filters, from_date, to_date)

	wb = openpyxl.Workbook(write_only=True)
	used_sheet_names = set()
	sheets_added = 0

	# openpyxl's write-only worksheets stream to disk as rows are appended and
	# can only be flushed by wb.save() once, at the very end — so every sheet
	# must be added to the *same* workbook before saving (unlike make_xlsx(),
	# which saves on every call and would corrupt earlier sheets here).
	for account in accounts:
		account_filters = frappe._dict(base_gl_filters)
		account_filters["account"] = json.dumps([account])

		columns, data = run_general_ledger(account_filters)
		if not data:
			continue

		sheet_name = get_unique_sheet_name(account, used_sheet_names)
		rows = build_sheet_rows(columns, data)
		add_sheet(wb, rows, sheet_name)
		sheets_added += 1

	if not sheets_added:
		frappe.throw(_("No General Ledger entries found for the selected accounts and filters"))

	xlsx_file = BytesIO()
	wb.save(xlsx_file)

	provide_binary_file(_("General Ledger - All Accounts"), "xlsx", xlsx_file.getvalue())


def add_sheet(wb, rows, sheet_name):
	"""Append `rows` (first row = header) as a new sheet on `wb`.

	Mirrors frappe.utils.xlsxutils.make_xlsx()'s row/date/HTML handling,
	minus the wb.save() call — write-only workbooks can only be saved once,
	so saving happens a single time after every sheet has been added.
	"""
	sheet_name = INVALID_TITLE_REGEX.sub(" ", sheet_name)
	ws = wb.create_sheet(sheet_name)
	ws.row_dimensions[1].font = Font(name="Calibri", bold=True)

	date_format, time_format = get_excel_date_format()

	for row in rows:
		clean_row = []
		for item in row:
			if isinstance(item, str):
				value = handle_html(item)
				if next(ILLEGAL_CHARACTERS_RE.finditer(value), None):
					value = ILLEGAL_CHARACTERS_RE.sub("", value)
			else:
				value = item

			if isinstance(value, datetime.date | datetime.datetime):
				number_format = date_format
				if isinstance(value, datetime.datetime):
					number_format = f"{date_format} {time_format}"

				cell = WriteOnlyCell(ws, value=value)
				cell.number_format = number_format
				clean_row.append(cell)
			else:
				clean_row.append(value)

		ws.append(clean_row)


def get_pnl_date_range(filters):
	period_list = get_period_list(
		filters.get("from_fiscal_year"),
		filters.get("to_fiscal_year"),
		filters.get("period_start_date"),
		filters.get("period_end_date"),
		filters.get("filter_based_on") or "Fiscal Year",
		"Yearly",
		company=filters.get("company"),
	)
	period = period_list[0]
	return period.year_start_date, period.year_end_date


def build_base_gl_filters(filters, from_date, to_date):
	gl_filters = frappe._dict(
		{
			"company": filters.get("company"),
			"from_date": from_date,
			"to_date": to_date,
			"finance_book": filters.get("finance_book"),
			"presentation_currency": filters.get("presentation_currency"),
			"include_default_book_entries": filters.get("include_default_book_entries", 1),
			"categorize_by": "Categorize by Voucher (Consolidated)",
			"show_opening_entries": 0,
		}
	)

	cost_center = filters.get("cost_center")
	if cost_center:
		gl_filters["cost_center"] = json.dumps(cost_center)

	project = filters.get("project")
	if project:
		gl_filters["project"] = json.dumps(project)

	return gl_filters


def build_sheet_rows(columns, data):
	visible_columns = [c for c in columns if not c.get("hidden")]
	header = [_(c.get("label") or c.get("fieldname")) for c in visible_columns]
	rows = [header]

	for d in data:
		row = []
		for c in visible_columns:
			value = d.get(c.get("fieldname"))
			if c.get("fieldtype") == "Currency" and value not in (None, ""):
				value = flt(value, 2)
			elif c.get("fieldtype") == "Date" and value:
				value = getdate(value)
			row.append(value)
		rows.append(row)

	return rows


def get_unique_sheet_name(account, used_sheet_names):
	name = account
	for ch in INVALID_SHEET_NAME_CHARS:
		name = name.replace(ch, " ")
	name = name.strip() or "Account"
	name = name[:MAX_SHEET_NAME_LENGTH]

	final_name = name
	suffix = 2
	while final_name.lower() in used_sheet_names:
		suffix_text = f" ({suffix})"
		final_name = name[: MAX_SHEET_NAME_LENGTH - len(suffix_text)] + suffix_text
		suffix += 1

	used_sheet_names.add(final_name.lower())
	return final_name
