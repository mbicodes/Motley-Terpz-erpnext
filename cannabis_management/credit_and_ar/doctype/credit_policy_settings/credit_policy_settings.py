import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CreditPolicySettings(Document):
	def validate(self):
		self._validate_thresholds()
		self._validate_finance_charge()
		self._validate_terms()
		self._normalise_lists()

	def on_update(self):
		# Every transaction reads these settings; the cache must not go stale.
		frappe.clear_document_cache("Credit Policy Settings", "Credit Policy Settings")

	# ── validation ───────────────────────────────────────────────────────────

	def _validate_thresholds(self):
		if flt(self.total_ar_cap) < 0:
			frappe.throw(_("Total AR Cap cannot be negative."))

		if self.dso_target_days and self.dso_breach_days:
			if self.dso_breach_days <= self.dso_target_days:
				frappe.throw(
					_("DSO Breach ({0} days) must be greater than DSO Target ({1} days).").format(
						self.dso_breach_days, self.dso_target_days
					)
				)

		if self.cei_target and self.cei_breach_below:
			if flt(self.cei_breach_below) >= flt(self.cei_target):
				frappe.throw(
					_("CEI Breach Below ({0}%) must be lower than CEI Target ({1}%).").format(
						self.cei_breach_below, self.cei_target
					)
				)

		if self.score_min and self.score_max and self.score_min >= self.score_max:
			frappe.throw(_("Score Minimum must be lower than Score Maximum."))

	def _validate_finance_charge(self):
		if not self.finance_charge_enabled:
			return

		missing = [
			label
			for label, value in (
				(_("Finance Charge Item"), self.finance_charge_item),
				(_("Finance Charge Income Account"), self.finance_charge_income_account),
			)
			if not value
		]
		if missing:
			frappe.throw(
				_("Finance charges cannot be enabled without: {0}").format(", ".join(missing))
			)

		if flt(self.monthly_rate) <= 0:
			frappe.throw(_("Monthly Rate must be greater than zero when finance charges are enabled."))

		if self.apply_to == "Per Payment Terms Template" and not self.finance_charge_templates:
			frappe.throw(
				_("List at least one Payment Terms Template when Apply To is 'Per Payment Terms Template'.")
			)

	def _validate_terms(self):
		if self.max_terms_days and self.max_terms_days <= 0:
			frappe.throw(_("Maximum Terms (Days) must be greater than zero."))

		if self.default_payment_terms_template and self.max_terms_days:
			days = _template_max_credit_days(self.default_payment_terms_template)
			if days > self.max_terms_days:
				frappe.throw(
					_("Default template {0} runs {1} days, beyond the {2}-day ceiling.").format(
						frappe.bold(self.default_payment_terms_template), days, self.max_terms_days
					)
				)

		for template in _split_csv(self.terms_requiring_md_exception):
			if not frappe.db.exists("Payment Terms Template", template):
				frappe.throw(
					_("Payment Terms Template {0} listed in 'Terms Requiring MD Exception' does not exist.").format(
						frappe.bold(template)
					)
				)

		for template in _split_csv(self.finance_charge_templates):
			if not frappe.db.exists("Payment Terms Template", template):
				frappe.throw(
					_("Payment Terms Template {0} listed in 'Finance Charge Templates' does not exist.").format(
						frappe.bold(template)
					)
				)

	def _normalise_lists(self):
		"""Store comma-separated lists in a canonical form so string matching is reliable."""
		if self.terms_requiring_md_exception:
			self.terms_requiring_md_exception = ",".join(_split_csv(self.terms_requiring_md_exception))
		if self.finance_charge_templates:
			self.finance_charge_templates = ",".join(_split_csv(self.finance_charge_templates))


def _split_csv(value: str | None) -> list[str]:
	if not value:
		return []
	return [part.strip() for part in value.split(",") if part.strip()]


def _template_max_credit_days(template: str) -> int:
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": template},
		pluck="credit_days",
	)
	return max([int(days or 0) for days in rows], default=0)
