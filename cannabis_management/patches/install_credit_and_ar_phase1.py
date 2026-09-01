"""Phase 1 of the Credit & AR Control module.

Idempotent: Customer credit fields, the payment-terms ladder, the finance-charge
item, permlevel-1 access, and the Credit Policy Settings defaults.

Note the two deliberate no-ops:
  * ``policy_effective_date`` is left blank — Finance sets it at go-live and every
    scheduled job stays inert until then.
  * Intercompany grouping is not configured. Intercompany trading is not in use,
    so no Customer Group is created and no Customer records are reassigned.
"""

import frappe

from cannabis_management.credit_and_ar import masters
from cannabis_management.credit_and_ar.custom_fields import install_phase_1_fields


def execute():
	install_phase_1_fields()
	masters.install_payment_terms_templates()
	item_code = masters.install_finance_charge_item()
	masters.install_permlevel_access()

	_seed_settings(item_code)
	_reset_customers_to_cod()


def _seed_settings(finance_charge_item: str | None):
	"""Populate defaults without overwriting anything Finance has already set."""
	settings = frappe.get_single("Credit Policy Settings")

	defaults = {
		"total_ar_cap": 400000,
		"dso_target_days": 14,
		"dso_breach_days": 30,
		"cei_target": 100,
		"cei_breach_below": 85,
		"warning_enabled": 1,
		"hard_hold_days": 5,
		"hard_hold_amount": 1000,
		"enhanced_review_threshold": 20000,
		"max_terms_days": 30,
		"monthly_rate": 1.5,
		"apply_to": "All Terms Invoices",
		"auto_submit_finance_charges": 0,
		"default_paydown_mode": "Percent of Order Value",
		"default_paydown_percent": 15,
		"workout_review_frequency_days": 30,
		"workout_no_shrink_days": 60,
		"score_min": 350,
		"score_max": 800,
		"qualifying_weekly_volume_g": 1000,
		"qualifying_weekly_volume_lbs": 100,
		"finance_notification_role": "Credit Finance",
	}

	for fieldname, value in defaults.items():
		if not settings.get(fieldname):
			settings.set(fieldname, value)

	if not settings.default_payment_terms_template and frappe.db.exists(
		"Payment Terms Template", "NET15"
	):
		settings.default_payment_terms_template = "NET15"

	if not settings.terms_requiring_md_exception:
		existing = frappe.get_all(
			"Payment Terms Template",
			filters={"name": ("in", masters.TERMS_REQUIRING_MD_EXCEPTION)},
			pluck="name",
		)
		settings.terms_requiring_md_exception = ",".join(sorted(existing))

	if finance_charge_item and not settings.finance_charge_item:
		settings.finance_charge_item = finance_charge_item

	for fieldname, user in (
		("managing_director", "imran@motleyterpz.com"),
		("ops_manager", "muhammad@motleyterpz.com"),
	):
		if settings.get(fieldname):
			continue
		if frappe.db.exists("User", user):
			settings.set(fieldname, user)
		else:
			frappe.logger("credit_and_ar").warning(
				f"User {user} does not exist — Credit Policy Settings.{fieldname} left blank."
			)

	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)


def _reset_customers_to_cod():
	"""Go-live position: every customer is COD until a credit line is approved.

	Only fills blanks, so re-running never clobbers a customer whose application
	has since been approved.
	"""
	frappe.db.sql(
		"""
		UPDATE `tabCustomer`
		SET custom_credit_status = %s
		WHERE custom_credit_status IS NULL OR custom_credit_status = ''
		""",
		("COD",),
	)
	frappe.db.sql(
		"""
		UPDATE `tabCustomer`
		SET custom_hold_type = %s
		WHERE custom_hold_type IS NULL OR custom_hold_type = ''
		""",
		("None",),
	)
