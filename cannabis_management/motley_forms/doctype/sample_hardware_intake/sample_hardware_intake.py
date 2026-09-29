# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Sample Hardware Intake — the paper SOP form, filled in once on the web.

The notification is sent from after_insert on this class rather than from a
doc_events entry in hooks.py, deliberately: it keeps the form entirely
self-contained, so it can be deployed without touching a shared file.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# Everyone who needs to see an intake the moment it is filed.
NOTIFY = [
	"nikki@motleyterpz.com",
	"tori@motleyterpz.com",
	"muhammad@motleyterpz.com",
	"leo@motleyterpz.com",
]

# Free samples are capped at this; anything larger is management's call.
FREE_SAMPLE_LIMIT_G = 5.0


class SampleHardwareIntake(Document):
	def validate(self):
		self.total_grams = flt(self.units_of_hardware) * flt(self.size_per_unit_g)
		# Recomputed on every save, so editing the order re-evaluates the gate
		# instead of leaving a stale flag behind.
		self.needs_approval = 1 if self.total_grams > FREE_SAMPLE_LIMIT_G else 0

		if not self.needs_approval and not self.approval_status:
			self.approval_status = "Pending"

		if self.other_oil and not self.other_oil_type:
			frappe.throw(_("Tick 'Other' and the oil type is required."))

		if not self.oil_types():
			frappe.throw(_("Pick at least one Type of Oil."))

	def oil_types(self):
		picked = []
		for fieldname, label in (("live_resin", "Live Resin"), ("distillate", "Distillate"),
		                         ("rosin", "Rosin")):
			if self.get(fieldname):
				picked.append(label)
		if self.other_oil and self.other_oil_type:
			picked.append(self.other_oil_type)
		return picked

	def after_insert(self):
		try:
			frappe.sendmail(
				recipients=NOTIFY,
				subject=self._subject(),
				message=self._body(),
				reference_doctype=self.doctype,
				reference_name=self.name,
			)
		except Exception:
			# A failed notification must never lose the submission itself.
			frappe.log_error(
				f"Sample Hardware Intake {self.name}: notification failed",
				"Sample Hardware Intake",
			)

	def _subject(self):
		flag = " — NEEDS APPROVAL (over 5g)" if self.needs_approval else ""
		return f"Sample Hardware Intake: {self.client_name}{flag}"

	def _body(self):
		esc = frappe.utils.escape_html
		rows = [
			("Client Name", self.client_name),
			("License Number", self.license_number),
			("Date Expected By", self.date_expected_by),
			("Date Dropped Off", self.date_dropped_off),
			("Type of Oil", ", ".join(self.oil_types())),
			("Units of Hardware", self.units_of_hardware),
			("Size per Unit (g)", self.size_per_unit_g),
			("Total", f"{flt(self.total_grams):g} g"),
			("Desired Strains", self.desired_strains),
		]
		body = "".join(
			f"<tr><td style='padding:6px 12px;color:#6b7280;font-size:12px;white-space:nowrap'>{label}</td>"
			f"<td style='padding:6px 12px;font-size:13px'><b>{esc(str(value)) if value not in (None, '') else '—'}</b></td></tr>"
			for label, value in rows
		)

		banner = ""
		if self.needs_approval:
			banner = (
				"<div style='background:#fff1e8;border-left:4px solid #c2410c;color:#7c2d12;"
				"padding:12px 14px;border-radius:6px;margin:0 0 16px;font-size:13px'>"
				f"<b>Over the {FREE_SAMPLE_LIMIT_G:g}g free-sample limit.</b><br>"
				"This order needs management approval before it is processed.</div>"
			)

		return (
			"<div style='font-family:Arial,Helvetica,sans-serif;color:#16181d'>"
			"<h2 style='margin:0 0 4px'>Sample Hardware Intake</h2>"
			f"<div style='color:#6b7280;font-size:12px;margin-bottom:16px'>{self.name}</div>"
			f"{banner}"
			f"<table style='border-collapse:collapse'>{body}</table>"
			f"<p style='margin-top:18px;font-size:12px'>"
			f"<a href='{frappe.utils.get_url_to_form(self.doctype, self.name)}'>Open in ERP</a></p>"
			"</div>"
		)
