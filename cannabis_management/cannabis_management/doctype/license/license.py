# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class License(Document):
	def validate(self):
		self.set_link_titles()

	def set_link_titles(self):
		"""Populate the read-only Link Title for each linked document row from the
		target doctype's title field (falls back to the record name)."""
		for row in self.links or []:
			if not (row.link_doctype and row.link_name):
				row.link_title = None
				continue
			title_field = frappe.get_meta(row.link_doctype).get_title_field()
			if title_field and title_field != "name":
				row.link_title = (
					frappe.db.get_value(row.link_doctype, row.link_name, title_field) or row.link_name
				)
			else:
				row.link_title = row.link_name
