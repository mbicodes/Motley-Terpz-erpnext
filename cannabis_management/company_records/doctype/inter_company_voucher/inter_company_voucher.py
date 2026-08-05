# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class InterCompanyVoucher(Document):
	def validate(self):
		self.validate_allocations()
		self.validate_bank_account()
		self.validate_mappings()

	def on_submit(self):
		if self.journal_entries:
			frappe.throw(_("Journal Entries have already been generated for this voucher."))
		self.create_intercompany_journal_entries()

	def on_cancel(self):
		self.cancel_linked_journal_entries()

	# ------------------------------------------------------------------
	# Validation
	# ------------------------------------------------------------------

	def validate_allocations(self):
		if not self.allocations:
			frappe.throw(_("Add at least one allocation row before saving."))

		allocation_total = 0
		for row in self.allocations:
			if not flt(row.amount) > 0:
				frappe.throw(_("Row #{0}: Amount must be greater than zero.").format(row.idx))

			expense_account_company = frappe.db.get_value("Account", row.expense_account, "company")
			if expense_account_company != row.company:
				frappe.throw(
					_("Row #{0}: Expense Account {1} does not belong to company {2}.")
					.format(row.idx, row.expense_account, row.company)
				)

			if row.cost_center:
				cost_center_company = frappe.db.get_value("Cost Center", row.cost_center, "company")
				if cost_center_company != row.company:
					frappe.throw(
						_("Row #{0}: Cost Center {1} does not belong to company {2}.")
						.format(row.idx, row.cost_center, row.company)
					)

			if row.project:
				project_company = frappe.db.get_value("Project", row.project, "company")
				if project_company and project_company != row.company:
					frappe.throw(
						_("Row #{0}: Project {1} does not belong to company {2}.")
						.format(row.idx, row.project, row.company)
					)

			allocation_total += flt(row.amount)

		if abs(allocation_total - flt(self.total_amount)) > 0.005:
			frappe.throw(
				_("Allocation total ({0}) must equal the Voucher Total Amount ({1}).")
				.format(allocation_total, self.total_amount)
			)

	def validate_bank_account(self):
		bank_account_company = frappe.db.get_value("Account", self.bank_account, "company")
		if bank_account_company != self.paying_company:
			frappe.throw(
				_("Bank Account {0} must belong to the Paying Company {1}.")
				.format(self.bank_account, self.paying_company)
			)

	def validate_mappings(self):
		for company in self.get_receiving_companies():
			mapping = frappe.db.get_value(
				"Inter Company Account Mapping",
				{"paying_company": self.paying_company, "receiving_company": company},
				["due_from_account", "due_to_account"],
				as_dict=True,
			)
			if not mapping or not mapping.due_from_account or not mapping.due_to_account:
				frappe.throw(
					_(
						"No Inter Company Account Mapping found for Paying Company {0} and "
						"Receiving Company {1}. Please configure it before submitting."
					).format(self.paying_company, company)
				)

	def get_receiving_companies(self):
		return sorted({row.company for row in self.allocations if row.company != self.paying_company})

	def get_allocations_by_company(self):
		by_company = {}
		for row in self.allocations:
			by_company.setdefault(row.company, []).append(row)
		return by_company

	# ------------------------------------------------------------------
	# Journal Entry generation
	# ------------------------------------------------------------------

	def create_intercompany_journal_entries(self):
		by_company = self.get_allocations_by_company()
		generated = []

		generated.append(self.make_paying_company_entry(by_company))

		for company in self.get_receiving_companies():
			generated.append(self.make_receiving_company_entry(company, by_company[company]))

		for company, role, je_name, amount in generated:
			self.append("journal_entries", {
				"company": company,
				"role": role,
				"journal_entry": je_name,
				"amount": amount,
			})

		self.update_child_table("journal_entries")

	def make_paying_company_entry(self, by_company):
		je = frappe.new_doc("Journal Entry")
		je.posting_date = self.posting_date
		je.company = self.paying_company
		je.party_not_required = 1
		je.user_remark = _("Inter Company Voucher {0}{1}").format(
			self.name, f" — {self.remarks}" if self.remarks else ""
		)

		for row in by_company.get(self.paying_company, []):
			je.append("accounts", {
				"account": row.expense_account,
				"cost_center": row.cost_center,
				"project": row.project,
				"debit_in_account_currency": row.amount,
				"user_remark": row.description,
			})

		for company in self.get_receiving_companies():
			due_from_account = frappe.db.get_value(
				"Inter Company Account Mapping",
				{"paying_company": self.paying_company, "receiving_company": company},
				"due_from_account",
			)
			amount = sum(flt(row.amount) for row in by_company[company])
			je.append("accounts", {
				"account": due_from_account,
				"debit_in_account_currency": amount,
				"user_remark": _("Intercompany receivable from {0}").format(company),
			})

		je.append("accounts", {
			"account": self.bank_account,
			"credit_in_account_currency": self.total_amount,
		})

		je.flags.ignore_permissions = True
		je.insert()
		je.submit()

		return (self.paying_company, "Paying Company", je.name, flt(self.total_amount))

	def make_receiving_company_entry(self, company, rows):
		due_to_account = frappe.db.get_value(
			"Inter Company Account Mapping",
			{"paying_company": self.paying_company, "receiving_company": company},
			"due_to_account",
		)
		amount = sum(flt(row.amount) for row in rows)

		je = frappe.new_doc("Journal Entry")
		je.posting_date = self.posting_date
		je.company = company
		je.party_not_required = 1
		je.user_remark = _("Inter Company Voucher {0} — expense paid by {1}").format(
			self.name, self.paying_company
		)

		for row in rows:
			je.append("accounts", {
				"account": row.expense_account,
				"cost_center": row.cost_center,
				"project": row.project,
				"debit_in_account_currency": row.amount,
				"user_remark": row.description,
			})

		je.append("accounts", {
			"account": due_to_account,
			"credit_in_account_currency": amount,
			"user_remark": _("Intercompany payable to {0}").format(self.paying_company),
		})

		je.flags.ignore_permissions = True
		je.insert()
		je.submit()

		return (company, "Receiving Company", je.name, amount)

	# ------------------------------------------------------------------
	# Cancellation
	# ------------------------------------------------------------------

	def cancel_linked_journal_entries(self):
		for row in self.journal_entries:
			je = frappe.get_doc("Journal Entry", row.journal_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				je.cancel()
