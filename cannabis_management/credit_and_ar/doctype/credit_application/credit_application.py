import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils

STATE_SUBMIT_FOR_REVIEW = "Submit for Review"
STATE_FINANCE_REVIEW = "Finance Review"
STATE_PENDING_MD = "Pending MD Approval"
STATE_APPROVED = "Approved"
STATE_REJECTED = "Rejected"
STATE_EXPIRED = "Expired"
STATE_REVOKED = "Revoked"

LIVE_STATES = (STATE_APPROVED,)
TERMINAL_STATES = (STATE_REJECTED, STATE_EXPIRED, STATE_REVOKED)

GENERIC_EMAIL_PREFIXES = (
	"info",
	"accounts",
	"accounting",
	"ap",
	"accountspayable",
	"billing",
	"admin",
	"office",
	"sales",
	"support",
	"contact",
	"hello",
	"finance",
	"payables",
	"invoices",
	"noreply",
	"no-reply",
)

class CreditApplication(Document):
	def validate(self):
		self._default_state()
		self._set_correspondence_defaults()
		self._sync_group_and_exposure()
		self._stamp_license_verification()
		self._flag_enhanced_assessment()
		self._validate_phone_country_code()
		self._validate_ap_contact()
		self._validate_state_requirements()

	def before_submit(self):
		if self.workflow_state == STATE_APPROVED:
			self._stamp_approval()

	@property
	def agreement_complete(self) -> bool:
		return bool(self.credit_agreement_signed and self.credit_agreement_document)

	def on_submit(self):
		if self.workflow_state == STATE_APPROVED:
			self.apply_approval()
			if not self.agreement_complete:
				self._notify_agreement_outstanding()
		elif self.workflow_state == STATE_REJECTED:
			self._notify_rejected()
		self._notify_requestor_of_decision()

	def on_update_after_submit(self):
		previous = self.get_doc_before_save()
		was = previous.workflow_state if previous else None

		if self.workflow_state == STATE_APPROVED and not self._is_live_on_customer():
			self.apply_approval()
			self.add_comment(
				"Info",
				_("Credit line synced to the customer record."),
			)

		if was == self.workflow_state:
			return

		if self.workflow_state in (STATE_REVOKED, STATE_EXPIRED) and was == STATE_APPROVED:
			self.apply_revocation()

	def on_cancel(self):
		if self.workflow_state == STATE_APPROVED:
			self.apply_revocation(reason=_("Credit Application cancelled."))

	def _default_state(self):
		if not self.workflow_state:
			self.workflow_state = STATE_SUBMIT_FOR_REVIEW

	def _set_correspondence_defaults(self):
		if not self.subject:
			self.subject = _("Credit Application — {0}").format(self.customer or "")

	def _sync_group_and_exposure(self):
		if not self.customer:
			return

		if not self.credit_group_parent:
			stored = frappe.db.get_value("Customer", self.customer, "custom_credit_group_parent")
			if stored:
				self.credit_group_parent = stored

		if self.credit_group_parent == self.customer:
			self.credit_group_parent = None

		anchor = self.credit_group_parent or self.customer
		self.group_existing_exposure = credit_engine.get_current_exposure(anchor)

		score, avg_days = frappe.db.get_value(
			"Customer", self.customer, ["custom_payment_score", "custom_avg_days_to_pay"]
		) or (None, None)
		self.historical_payment_score = score
		self.historical_avg_days_to_pay = avg_days

	def _stamp_license_verification(self):
		if self.license_verified and not self.license_verified_by:
			self.license_verified_by = frappe.session.user
			self.license_verified_on = nowdate()
		elif not self.license_verified:
			self.license_verified_by = None
			self.license_verified_on = None

	def _flag_enhanced_assessment(self):
		threshold = flt(utils.get_settings().enhanced_review_threshold)
		self.requires_enhanced_assessment = int(
			bool(threshold and flt(self.recommended_limit) > threshold)
		)

	def _validate_phone_country_code(self):
		for fieldname, label in (
			("requestor_phone", _("Phone Number")),
			("ap_contact", _("AP Contact")),
		):
			phone = (self.get(fieldname) or "").strip()
			self.set(fieldname, phone)
			if phone and not phone.startswith("+"):
				frappe.throw(
					_(
						"<b>{0}</b> needs a country code, e.g. +1 415 555 0100.<br><br>"
						"Add a leading <b>+</b> and the country code before the number."
					).format(frappe.utils.escape_html(phone)),
					title=label,
				)

	def _validate_ap_contact(self):
		if self.ap_contact_email:
			self._validate_ap_email()

	def _validate_ap_email(self):
		email = (self.ap_contact_email or "").strip().lower()
		self.ap_contact_email = email

		if "@" not in email:
			frappe.throw(_("{0} is not a valid email address.").format(email), title=_("AP Contact"))

		local = email.split("@", 1)[0]
		normalised = re.sub(r"[._-]", "", local)

		if normalised in GENERIC_EMAIL_PREFIXES:
			frappe.throw(
				_(
					"<b>{0}</b> is a shared inbox, not an AP contact.<br><br>"
					"Policy requires a named person in Accounts Payable with a direct email "
					"address. Generic addresses such as info@, ap@, accounts@ and billing@ "
					"are not accepted."
				).format(frappe.utils.escape_html(email)),
				title=_("AP Contact Email"),
			)

	def _validate_state_requirements(self):
		if self.workflow_state == STATE_FINANCE_REVIEW:
			self._validate_applicant_submission()
		elif self.workflow_state == STATE_PENDING_MD:
			self._validate_recommendation()
		elif self.workflow_state == STATE_APPROVED:
			self._validate_recommendation()
			self._validate_approval()

	def _validate_applicant_submission(self):
		problems = []

		if not self.ap_contact_name:
			problems.append(_("AP contact name is missing."))
		if not self.ap_contact_email:
			problems.append(_("AP contact email is missing."))

		utils.throw_consolidated(problems, "AP Contact Required")

	def _validate_recommendation(self):
		problems = []

		required = [
			("exact_legal_buyer", _("Exact legal buyer (the legal entity, not the DBA)")),
			("legal_entity_type", _("Legal entity type")),
			("license_number", _("License number")),
			("license_expiry_date", _("License expiry date")),
			("expected_weekly_volume", _("Expected weekly volume")),
			("expected_monthly_revenue", _("Expected monthly revenue")),
		]
		for fieldname, label in required:
			if not self.get(fieldname):
				problems.append(_("{0} is required.").format(label))

		if not self.license_verified:
			problems.append(_("The license has not been verified."))

		if self.license_expiry_date and getdate(self.license_expiry_date) < getdate(nowdate()):
			problems.append(
				_("The license expired on {0}. An expired license cannot support a credit line.").format(
					frappe.format(self.license_expiry_date, {"fieldtype": "Date"})
				)
			)

		if flt(self.recommended_limit) <= 0:
			problems.append(_("Recommended limit must be greater than zero."))

		if not self.recommended_terms:
			problems.append(_("Recommended terms are required."))

		if self.requires_enhanced_assessment and not self.enhanced_assessment_notes:
			problems.append(
				_(
					"Enhanced assessment notes are required — the recommended limit exceeds {0}."
				).format(
					utils.fmt_currency(utils.get_settings().enhanced_review_threshold)
				)
			)

		utils.throw_consolidated(problems, "Cannot Recommend — Credit File Incomplete")

	def _validate_approval(self):
		settings = utils.get_settings()
		problems = []

		if flt(self.approved_limit) <= 0:
			problems.append(_("Approved limit must be greater than zero."))

		if not self.approved_terms:
			problems.append(_("Approved terms are required."))
		else:
			days = utils.template_credit_days(self.approved_terms)
			ceiling = int(settings.max_terms_days or 0)
			if ceiling and days > ceiling:
				problems.append(
					_("{0} runs {1} days, beyond the {2}-day ceiling. Nothing beyond Net {2}, ever.").format(
						self.approved_terms, days, ceiling
					)
				)

		if self.license_expiry_date and getdate(self.license_expiry_date) < getdate(nowdate()):
			problems.append(_("The license has expired."))

		utils.throw_consolidated(problems, "Cannot Approve — Requirements Outstanding")

	def _stamp_approval(self):
		self.md_approved = 1
		self.approved_by = frappe.session.user
		self.approved_on = now_datetime()

	def _is_live_on_customer(self) -> bool:
		return (
			frappe.db.get_value("Customer", self.customer, "custom_active_credit_application")
			== self.name
		)

	def _notify_agreement_outstanding(self):
		self.add_comment(
			"Info",
			_(
				"Approved by the Managing Director. <b>Terms are now live</b> for this "
				"customer. The signed Credit Agreement is still outstanding — attach it "
				"to close out the file."
			),
		)
		self._notify_awaiting_agreement()

	def _notify_awaiting_agreement(self):
		recipients = utils.dedupe_recipients(self.owner, utils.finance_recipients())
		if not recipients:
			return

		self._sendmail(
			recipients,
			_("Credit line approved — signed agreement still outstanding — {0}").format(self.customer),
			_(
				"<p>The Managing Director has approved a <b>{limit}</b> line on "
				"<b>{terms}</b> for <b>{customer}</b>, and terms are already live on the "
				"account.</p>"
				"<p style='color:#b91c1c;'><b>The signed Credit Agreement is still "
				"outstanding.</b> Please get it signed and attached to the application to "
				"close out the file.</p><p>{link}</p>"
			).format(
				limit=utils.fmt_currency(self.approved_limit),
				terms=frappe.utils.escape_html(self.approved_terms or ""),
				customer=frappe.utils.escape_html(self.customer),
				link=utils.doc_link("Credit Application", self.name),
			),
		)

	def apply_approval(self):
		self._supersede_previous_applications()
		self._upsert_credit_limit()
		self._update_customer(live=True)
		self._notify_approved()

	def _supersede_previous_applications(self):
		members = credit_engine.get_credit_group_members(self.customer)
		siblings = frappe.get_all(
			"Credit Application",
			filters={
				"name": ("!=", self.name),
				"customer": ("in", members),
				"docstatus": 1,
				"workflow_state": STATE_APPROVED,
			},
			pluck="name",
		)
		for name in siblings:
			frappe.db.set_value(
				"Credit Application",
				name,
				{"workflow_state": STATE_REVOKED},
				update_modified=False,
			)
			frappe.get_doc("Credit Application", name).add_comment(
				"Info", _("Superseded by {0}.").format(self.name)
			)

	def _upsert_credit_limit(self):
		if utils.is_policy_exempt(self.customer):
			return

		_write_credit_limit(self.customer, utils.company_of(self.customer), flt(self.approved_limit))

	def _update_customer(self, live: bool):
		exempt = utils.is_policy_exempt(self.customer)

		values = {
			"custom_active_credit_application": self.name if live else None,
			"custom_credit_terms_template": self.approved_terms if live else None,
			"custom_terms_valid_until": None,
			"custom_approved_credit_limit": flt(self.approved_limit) if live else 0,
			"payment_terms": self.approved_terms if live else None,
		}

		if not exempt:
			values["custom_credit_status"] = (
				utils.STATUS_TERMS_APPROVED if live else utils.STATUS_COD
			)

		if live:
			values.update(
				{
					"custom_license_number": self.license_number,
					"custom_license_expiry": self.license_expiry_date,
					"custom_ap_contact_name": self.ap_contact_name,
					"custom_ap_contact_phone": self.ap_contact,
					"custom_ap_contact_email": self.ap_contact_email,
				}
			)
			if self.credit_group_parent:
				values["custom_credit_group_parent"] = self.credit_group_parent

		current_status = frappe.db.get_value("Customer", self.customer, "custom_credit_status")
		if live and current_status in utils.CASE_DRIVEN_STATUSES:
			values.pop("custom_credit_status", None)

		frappe.db.set_value("Customer", self.customer, values, update_modified=False)

		parent = credit_engine.get_credit_group_parent(self.customer)
		if parent and parent != self.customer:
			frappe.db.set_value(
				"Customer",
				parent,
				{"custom_approved_credit_limit": flt(self.approved_limit) if live else 0},
				update_modified=False,
			)

		credit_engine.refresh_customer_exposure(self.customer)

	def apply_revocation(self, reason: str | None = None):
		if reason:
			self.add_comment("Info", reason)

		self._update_customer(live=False)
		self._zero_credit_limit()
		self._reopen_terms_sales_orders()
		self._notify_revoked(reason)

	def _zero_credit_limit(self):
		_write_credit_limit(self.customer, utils.company_of(self.customer), 0)

	def _reopen_terms_sales_orders(self):
		orders = frappe.get_all(
			"Sales Order",
			filters={
				"customer": self.customer,
				"docstatus": 0,
				"custom_mode_of_payment": utils.MODE_TERMS,
			},
			pluck="name",
		)
		for name in orders:
			frappe.db.set_value(
				"Sales Order",
				name,
				{"custom_approval_status": utils.APPROVAL_PENDING},
				update_modified=False,
			)

	def _notify_approved(self):
		recipients = utils.dedupe_recipients(
			self.owner,
			utils.finance_recipients(),
			utils.users_with_role("Sales Manager"),
		)
		if not recipients:
			return

		message = _(
			"""
			<p>The credit line for <b>{customer}</b> is now live.</p>
			<table style="font-size:14px;margin:8px 0;">
				<tr><td style="padding:2px 12px 2px 0;color:#666;">Approved Limit</td><td><b>{limit}</b></td></tr>
				<tr><td style="padding:2px 12px 2px 0;color:#666;">Terms</td><td>{terms}</td></tr>
				<tr><td style="padding:2px 12px 2px 0;color:#666;">Approved By</td><td>{approver}</td></tr>
			</table>
			<p>{application}</p>
			<p style="color:#666;font-size:13px;">Terms Sales Orders still require per-order
			approval from the Managing Director or Ops Manager.</p>
			"""
		).format(
			customer=frappe.utils.escape_html(self.customer),
			limit=utils.fmt_currency(self.approved_limit),
			terms=frappe.utils.escape_html(self.approved_terms or ""),
			approver=frappe.utils.get_fullname(self.approved_by),
			application=utils.doc_link("Credit Application", self.name),
		)

		self._sendmail(
			recipients,
			_("Credit line approved — {0}").format(self.customer),
			message,
		)

	def _notify_rejected(self):
		recipients = utils.dedupe_recipients(self.owner, utils.finance_recipients())
		if not recipients:
			return
		self._sendmail(
			recipients,
			_("Credit application rejected — {0}").format(self.customer),
			_("<p>The credit application for <b>{0}</b> was rejected. {1}</p>").format(
				frappe.utils.escape_html(self.customer),
				utils.doc_link("Credit Application", self.name),
			),
		)

	def _notify_revoked(self, reason: str | None = None):
		recipients = utils.dedupe_recipients(
			self.owner,
			utils.finance_recipients(),
			utils.routed_user("managing_director"),
			utils.users_with_role("Sales Manager"),
		)
		if not recipients:
			return
		self._sendmail(
			recipients,
			_("Credit line withdrawn — {0}").format(self.customer),
			_(
				"<p>The credit line for <b>{0}</b> is no longer live — the account is back "
				"to <b>COD</b> and the limit is zero.</p><p>Reason: {1}</p><p>{2}</p>"
			).format(
				frappe.utils.escape_html(self.customer),
				frappe.utils.escape_html(reason or _("not recorded")),
				utils.doc_link("Credit Application", self.name),
			),
		)

	def _notify_requestor_of_decision(self):
		if not self.requestor_email:
			return

		applicant = frappe.utils.escape_html(
			self.requestor_name or self.exact_legal_buyer or self.customer or ""
		)

		if self.workflow_state == STATE_APPROVED:
			subject = _("Your credit application has been approved — {0}").format(
				self.exact_legal_buyer or self.customer or ""
			)
			message = _(
				"""
				<p>Hi {applicant},</p>
				<p>Good news — your credit application has been <b>approved</b>. A copy of your
				signed Credit Agreement is attached for your records.</p>
				<table style="font-size:14px;margin:8px 0;">
					<tr><td style="padding:2px 12px 2px 0;color:#666;">Approved Limit</td><td><b>{limit}</b></td></tr>
					<tr><td style="padding:2px 12px 2px 0;color:#666;">Payment Terms</td><td>{terms}</td></tr>
				</table>
				<p>If anything above looks off, just reply to this email and our finance team
				will help. Thanks for choosing to work with us.</p>
				"""
			).format(
				applicant=applicant,
				limit=utils.fmt_currency(self.approved_limit),
				terms=frappe.utils.escape_html(self.approved_terms or ""),
			)
		else:
			subject = _("An update on your credit application — {0}").format(
				self.exact_legal_buyer or self.customer or ""
			)
			message = _(
				"""
				<p>Hi {applicant},</p>
				<p>Thank you for applying for a credit line with us. After review, we're not
				able to approve one at this time. A copy of your submitted application is
				attached for your records.</p>
				<p>You're welcome to order with us on a cash/COD basis in the meantime, and to
				re-apply later if your circumstances change. Reply to this email if you have
				any questions.</p>
				"""
			).format(applicant=applicant)

		try:
			attachment = frappe.attach_print(self.doctype, self.name, print_format="Credit Agreement")
			frappe.sendmail(
				recipients=[self.requestor_email],
				subject=subject,
				message=message,
				attachments=[attachment],
				reference_doctype=self.doctype,
				reference_name=self.name,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Credit Application requestor notification failed")

	def _sendmail(self, recipients: list[str], subject: str, message: str):
		try:
			frappe.sendmail(
				recipients=recipients,
				subject=subject,
				message=message,
				reference_doctype=self.doctype,
				reference_name=self.name,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Credit Application notification failed")


def _write_credit_limit(customer: str, company: str, limit: float):
	if not company:
		frappe.logger("credit_and_ar").warning(
			f"No company could be derived for {customer} — native credit limit row not written."
		)
		return

	if not frappe.db.exists("Company", company):
		return

	row = frappe.db.get_value(
		"Customer Credit Limit",
		{"parent": customer, "parenttype": "Customer", "company": company},
		"name",
	)

	if row:
		frappe.db.set_value(
			"Customer Credit Limit",
			row,
			{"credit_limit": flt(limit), "bypass_credit_limit_check": 1},
			update_modified=False,
		)
	else:
		child = frappe.new_doc("Customer Credit Limit")
		child.parent = customer
		child.parenttype = "Customer"
		child.parentfield = "credit_limits"
		child.company = company
		child.credit_limit = flt(limit)
		child.bypass_credit_limit_check = 1
		child.idx = (
			frappe.db.count("Customer Credit Limit", {"parent": customer, "parenttype": "Customer"})
			+ 1
		)
		child.insert(ignore_permissions=True)

	frappe.clear_document_cache("Customer", customer)
