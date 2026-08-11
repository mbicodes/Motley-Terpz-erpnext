"""Custom field definitions for the Credit & AR Control module.

Fields are declared here and applied idempotently by the module's patches, so a
plain ``bench migrate`` reproduces them on any site. They are also exported
through the app's existing unfiltered ``Custom Field`` fixture.

Naming policy: the module does **not** introduce a second order-type or payment
mode field. ``custom_sales_order_type`` and ``custom_mode_of_payment`` already
exist on Sales Order and already drive print formats and dashboards, so the
credit gate reads those (see ``utils.resolve_order_type``). Likewise
``custom_license_number`` and ``custom_license_expiry`` already exist on
Customer and are reused as-is.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CREDIT_STATUS_OPTIONS = (
	"COD\nTerms Approved\nWarning\nHard Hold\nPayment Plan\nWorkout\nBlocked\nPolicy Exempt"
)
HOLD_TYPE_OPTIONS = "None\nWarning\nHard Hold\nImmediate Hold"
SCORE_BAND_OPTIONS = "Insufficient History\nExcellent\nGood\nFair\nWatch\nCOD Only"


CUSTOMER_FIELDS = [
	{
		"fieldname": "custom_credit_control_tab",
		"fieldtype": "Tab Break",
		"label": "Credit Control",
		"insert_after": "custom_notebox",
	},
	# ── Exemption ────────────────────────────────────────────────────────
	# The escape hatch, deliberately first: anyone opening this tab should see
	# immediately whether the policy applies at all.
	{
		"fieldname": "custom_credit_exemption_section",
		"fieldtype": "Section Break",
		"label": "Policy Exemption",
		"insert_after": "custom_credit_control_tab",
	},
	{
		"fieldname": "custom_credit_policy_exempt",
		"fieldtype": "Check",
		"label": "Exempt from Credit &amp; AR Policy",
		"default": "0",
		"permlevel": 1,
		"in_standard_filter": 1,
		"description": (
			"Switches this module off for this account entirely: no Sales Order gate, "
			"no holds, no AR Cases, no ledger enforcement, no finance charges, no scoring. "
			"Their balance still counts toward the company AR cap, DSO and CEI. "
			"Only Credit Finance and the Managing Director can set this."
		),
		"insert_after": "custom_credit_exemption_section",
	},
	{
		"fieldname": "custom_credit_exemption_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_credit_policy_exempt",
	},
	{
		"fieldname": "custom_credit_policy_exempt_reason",
		"fieldtype": "Small Text",
		"label": "Exemption Reason",
		"permlevel": 1,
		"depends_on": "custom_credit_policy_exempt",
		"mandatory_depends_on": "custom_credit_policy_exempt",
		"description": "Why this account is outside the policy, and who authorised it.",
		"insert_after": "custom_credit_exemption_cb",
	},
	# ── Standing ─────────────────────────────────────────────────────────
	{
		"fieldname": "custom_credit_standing_section",
		"fieldtype": "Section Break",
		"label": "Standing",
		"insert_after": "custom_credit_policy_exempt_reason",
	},
	{
		"fieldname": "custom_credit_status",
		"fieldtype": "Select",
		"label": "Credit Status",
		"options": CREDIT_STATUS_OPTIONS,
		"default": "COD",
		"read_only": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
		"description": "Every customer is COD by default. Terms are granted only through an approved Credit Application.",
		"insert_after": "custom_credit_standing_section",
	},
	{
		"fieldname": "custom_approved_credit_limit",
		"fieldtype": "Currency",
		"label": "Approved Credit Limit",
		"read_only": 1,
		"description": "Group-wide limit, shared across all operating companies.",
		"insert_after": "custom_credit_status",
	},
	{
		"fieldname": "custom_terms_valid_until",
		"fieldtype": "Date",
		"label": "Terms Valid Until",
		"read_only": 1,
		"insert_after": "custom_approved_credit_limit",
	},
	{
		"fieldname": "custom_credit_standing_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_terms_valid_until",
	},
	{
		"fieldname": "custom_credit_terms_template",
		"fieldtype": "Link",
		"label": "Approved Payment Terms",
		"options": "Payment Terms Template",
		"read_only": 1,
		"permlevel": 1,
		"description": "One term per account. Set by the approved Credit Application; Sales cannot change it.",
		"insert_after": "custom_credit_standing_cb",
	},
	{
		"fieldname": "custom_current_exposure",
		"fieldtype": "Currency",
		"label": "Current Exposure",
		"read_only": 1,
		"description": "Open invoice balances plus unbilled Terms orders, across the whole credit group.",
		"insert_after": "custom_credit_terms_template",
	},
	{
		"fieldname": "custom_available_line",
		"fieldtype": "Currency",
		"label": "Available Line",
		"read_only": 1,
		"insert_after": "custom_current_exposure",
	},
	# ── Grouping ─────────────────────────────────────────────────────────
	{
		"fieldname": "custom_credit_group_section",
		"fieldtype": "Section Break",
		"label": "Related Entities",
		"insert_after": "custom_available_line",
	},
	{
		"fieldname": "custom_credit_group_parent",
		"fieldtype": "Link",
		"label": "Credit Group Parent",
		"options": "Customer",
		"description": "Related entities share one revolving line. Leave blank if this customer stands alone.",
		"insert_after": "custom_credit_group_section",
	},
	{
		"fieldname": "custom_credit_group_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_credit_group_parent",
	},
	{
		"fieldname": "custom_is_intercompany",
		"fieldtype": "Check",
		"label": "Is Intercompany",
		"default": "0",
		"description": "Excluded from client-facing credit reports. Intercompany trading is not in use; this stays unticked unless that changes.",
		"insert_after": "custom_credit_group_cb",
	},
	# ── Hold state ───────────────────────────────────────────────────────
	{
		"fieldname": "custom_hold_section",
		"fieldtype": "Section Break",
		"label": "Stop Work",
		"insert_after": "custom_is_intercompany",
	},
	{
		"fieldname": "custom_on_hold",
		"fieldtype": "Check",
		"label": "On Hold",
		"default": "0",
		"read_only": 1,
		"in_standard_filter": 1,
		"insert_after": "custom_hold_section",
	},
	{
		"fieldname": "custom_hold_type",
		"fieldtype": "Select",
		"label": "Hold Type",
		"options": HOLD_TYPE_OPTIONS,
		"default": "None",
		"read_only": 1,
		"insert_after": "custom_on_hold",
	},
	{
		"fieldname": "custom_hold_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_hold_type",
	},
	{
		"fieldname": "custom_hold_since",
		"fieldtype": "Date",
		"label": "On Hold Since",
		"read_only": 1,
		"insert_after": "custom_hold_cb",
	},
	{
		"fieldname": "custom_returned_payment_count",
		"fieldtype": "Int",
		"label": "Returned Payments",
		"default": "0",
		"read_only": 1,
		"insert_after": "custom_hold_since",
	},
	{
		"fieldname": "custom_broken_ptp_count",
		"fieldtype": "Int",
		"label": "Broken Promises to Pay",
		"default": "0",
		"read_only": 1,
		"insert_after": "custom_returned_payment_count",
	},
	# ── Scoring ──────────────────────────────────────────────────────────
	{
		"fieldname": "custom_score_section",
		"fieldtype": "Section Break",
		"label": "Payment Score",
		"insert_after": "custom_broken_ptp_count",
	},
	{
		"fieldname": "custom_payment_score",
		"fieldtype": "Int",
		"label": "Payment Score",
		"read_only": 1,
		"description": "350–800. Blank until the customer has at least three paid invoices.",
		"insert_after": "custom_score_section",
	},
	{
		"fieldname": "custom_score_band",
		"fieldtype": "Select",
		"label": "Score Band",
		"options": SCORE_BAND_OPTIONS,
		"read_only": 1,
		"in_standard_filter": 1,
		"insert_after": "custom_payment_score",
	},
	{
		"fieldname": "custom_score_last_updated",
		"fieldtype": "Datetime",
		"label": "Score Last Updated",
		"read_only": 1,
		"insert_after": "custom_score_band",
	},
	{
		"fieldname": "custom_score_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_score_last_updated",
	},
	{
		"fieldname": "custom_avg_days_to_pay",
		"fieldtype": "Float",
		"label": "Avg Days to Pay",
		"precision": "1",
		"read_only": 1,
		"description": "Signed, relative to the due date. Negative means the customer pays early.",
		"insert_after": "custom_score_cb",
	},
	{
		"fieldname": "custom_on_time_percent",
		"fieldtype": "Percent",
		"label": "On-Time %",
		"read_only": 1,
		"insert_after": "custom_avg_days_to_pay",
	},
	{
		"fieldname": "custom_weekly_volume_g",
		"fieldtype": "Float",
		"label": "Weekly Volume (g)",
		"precision": "2",
		"read_only": 1,
		"description": "Trailing four-week average.",
		"insert_after": "custom_on_time_percent",
	},
	{
		"fieldname": "custom_weekly_volume_lbs",
		"fieldtype": "Float",
		"label": "Weekly Volume (lbs)",
		"precision": "2",
		"read_only": 1,
		"insert_after": "custom_weekly_volume_g",
	},
	# ── Credit file ──────────────────────────────────────────────────────
	{
		"fieldname": "custom_credit_file_section",
		"fieldtype": "Section Break",
		"label": "Credit File",
		"insert_after": "custom_weekly_volume_lbs",
	},
	{
		"fieldname": "custom_license_verified",
		"fieldtype": "Check",
		"label": "License Verified (Credit File)",
		"default": "0",
		"read_only": 1,
		"description": "Verified as part of the credit file. Distinct from METRC license verification.",
		"insert_after": "custom_credit_file_section",
	},
	{
		"fieldname": "custom_reconciliation_clause_ack",
		"fieldtype": "Check",
		"label": "Reconciliation Clause Acknowledged",
		"default": "0",
		"read_only": 1,
		"description": "The customer accepts that we may request their ledger any time a balance is open; refusal suspends terms.",
		"insert_after": "custom_license_verified",
	},
	{
		"fieldname": "custom_credit_file_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_reconciliation_clause_ack",
	},
	{
		"fieldname": "custom_ap_contact_name",
		"fieldtype": "Data",
		"label": "AP Contact Name",
		"insert_after": "custom_credit_file_cb",
	},
	{
		"fieldname": "custom_ap_contact_phone",
		"fieldtype": "Data",
		"label": "AP Contact Direct Line",
		"insert_after": "custom_ap_contact_name",
	},
	{
		"fieldname": "custom_ap_contact_email",
		"fieldtype": "Data",
		"label": "AP Contact Email",
		"options": "Email",
		"insert_after": "custom_ap_contact_phone",
	},
]


PHASE_1_FIELDS = {
	"Customer": CUSTOMER_FIELDS,
}


# ── Phase 2 ──────────────────────────────────────────────────────────────────
# Applied only once the Credit Application DocType exists, since these are Link
# fields pointing at it.

PHASE_2_FIELDS = {
	"Customer": [
		{
			"fieldname": "custom_active_credit_application",
			"fieldtype": "Link",
			"label": "Active Credit Application",
			"options": "Credit Application",
			"read_only": 1,
			"description": "The approved application currently granting this account terms.",
			"insert_after": "custom_credit_status",
		},
	],
}


# ── Phase 3 ──────────────────────────────────────────────────────────────────
# The Sales Order gate. No new order-type or payment-mode field: the gate reads
# custom_sales_order_type and custom_mode_of_payment, which already exist.

LEDGER_OPTIONS = "\nNew Book\nLegacy\nPlan\nWorkout Paydown\nDeposit"

SALES_ORDER_FIELDS = [
	{
		"fieldname": "custom_credit_section",
		"fieldtype": "Section Break",
		"label": "Credit Control",
		"insert_after": "custom_mode_of_payment",
		"collapsible": 1,
	},
	{
		"fieldname": "custom_credit_application",
		"fieldtype": "Link",
		"label": "Credit Application",
		"options": "Credit Application",
		"read_only": 1,
		"insert_after": "custom_credit_section",
	},
	{
		"fieldname": "custom_customer_available_line",
		"fieldtype": "Currency",
		"label": "Available Line",
		"read_only": 1,
		"description": "Group-wide, across every operating company, excluding this order.",
		"insert_after": "custom_credit_application",
	},
	{
		"fieldname": "custom_required_deposit",
		"fieldtype": "Currency",
		"label": "Required Deposit",
		"read_only": 1,
		"description": "The template's up-front leg plus any amount over the available line. Must clear before submit.",
		"insert_after": "custom_customer_available_line",
	},
	{
		"fieldname": "custom_deposit_received",
		"fieldtype": "Currency",
		"label": "Deposit Cleared Amount",
		"read_only": 1,
		"insert_after": "custom_required_deposit",
	},
	{
		"fieldname": "custom_deposit_cleared",
		"fieldtype": "Check",
		"label": "Deposit Cleared",
		"default": "0",
		"read_only": 1,
		"insert_after": "custom_deposit_received",
	},
	{
		"fieldname": "custom_credit_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_deposit_cleared",
	},
	{
		"fieldname": "custom_terms_requested_on",
		"fieldtype": "Datetime",
		"label": "Terms Requested On",
		"read_only": 1,
		"insert_after": "custom_credit_cb",
	},
	{
		"fieldname": "custom_terms_approved_by",
		"fieldtype": "Link",
		"label": "Terms Decided By",
		"options": "User",
		"read_only": 1,
		"insert_after": "custom_terms_requested_on",
	},
	{
		"fieldname": "custom_terms_approved_on",
		"fieldtype": "Datetime",
		"label": "Terms Decided On",
		"read_only": 1,
		"insert_after": "custom_terms_approved_by",
	},
	{
		"fieldname": "custom_terms_rejection_reason",
		"fieldtype": "Small Text",
		"label": "Rejection Reason",
		"read_only": 1,
		"depends_on": "custom_terms_rejection_reason",
		"insert_after": "custom_terms_approved_on",
	},
	{
		"fieldname": "custom_print_blocked",
		"fieldtype": "Check",
		"label": "Print Blocked",
		"default": "0",
		"read_only": 1,
		"description": "Set while a Terms order is unapproved. Enforced server-side on every print and PDF route.",
		"insert_after": "custom_terms_rejection_reason",
	},
	{
		"fieldname": "custom_workout_paydown_required",
		"fieldtype": "Currency",
		"label": "Workout Paydown Required",
		"read_only": 1,
		"depends_on": "custom_workout_paydown_required",
		"insert_after": "custom_print_blocked",
	},
	{
		"fieldname": "custom_workout_paydown_received",
		"fieldtype": "Currency",
		"label": "Workout Paydown Received",
		"read_only": 1,
		"depends_on": "custom_workout_paydown_required",
		"insert_after": "custom_workout_paydown_required",
	},
]

# Needed now rather than in phase 5: the submit gate cannot verify a cleared
# deposit without somewhere to record one.
PAYMENT_ENTRY_FIELDS = [
	{
		"fieldname": "custom_credit_section",
		"fieldtype": "Section Break",
		"label": "Credit & AR",
		"insert_after": "reference_no",
		"collapsible": 1,
	},
	{
		"fieldname": "custom_ledger",
		"fieldtype": "Select",
		"label": "Ledger",
		"options": LEDGER_OPTIONS,
		"depends_on": "eval:doc.payment_type=='Receive' && doc.party_type=='Customer'",
		"description": "Which book this receipt belongs to. Plan and New Book money is never netted.",
		"insert_after": "custom_credit_section",
	},
	{
		"fieldname": "custom_against_sales_order",
		"fieldtype": "Link",
		"label": "Against Sales Order",
		"options": "Sales Order",
		"depends_on": "eval:['Deposit','Workout Paydown'].includes(doc.custom_ledger)",
		"description": "Required for a deposit or a workout paydown, so the submit gate can find it.",
		"insert_after": "custom_ledger",
	},
	{
		"fieldname": "custom_credit_cb",
		"fieldtype": "Column Break",
		"insert_after": "custom_against_sales_order",
	},
	{
		"fieldname": "custom_is_returned_payment",
		"fieldtype": "Check",
		"label": "Returned / Bounced Payment",
		"default": "0",
		"description": "Tick before cancelling when the payment was returned by the bank. Triggers an immediate hold — an ordinary correction does not.",
		"insert_after": "custom_credit_cb",
	},
	{
		"fieldname": "custom_return_reason",
		"fieldtype": "Small Text",
		"label": "Return Reason",
		"depends_on": "custom_is_returned_payment",
		"insert_after": "custom_is_returned_payment",
	},
]

SALES_INVOICE_FIELDS = [
	{
		"fieldname": "custom_ledger",
		"fieldtype": "Select",
		"label": "Ledger",
		"options": "\nNew Book\nLegacy\nPlan",
		"read_only": 1,
		"description": "Legacy when the posting date precedes the policy effective date. Legacy is collected on original terms and never carries finance charges.",
		"insert_after": "custom_order_type",
	},
	{
		"fieldname": "custom_is_finance_charge",
		"fieldtype": "Check",
		"label": "Is Finance Charge",
		"default": "0",
		"read_only": 1,
		"insert_after": "custom_ledger",
	},
	{
		"fieldname": "custom_finance_charge_against",
		"fieldtype": "Link",
		"label": "Finance Charge Against",
		"options": "Sales Invoice",
		"read_only": 1,
		"depends_on": "custom_is_finance_charge",
		"insert_after": "custom_is_finance_charge",
	},
	{
		"fieldname": "custom_finance_charge_applied_upto",
		"fieldtype": "Date",
		"label": "Finance Charge Applied Up To",
		"read_only": 1,
		"insert_after": "custom_finance_charge_against",
	},
]

PHASE_3_FIELDS = {
	"Sales Order": SALES_ORDER_FIELDS,
	"Payment Entry": PAYMENT_ENTRY_FIELDS,
	"Sales Invoice": SALES_INVOICE_FIELDS,
}


# ── Phase 4 ──────────────────────────────────────────────────────────────────
# Link fields pointing at AR Case, so they can only be created once that DocType
# exists.

PHASE_4_FIELDS = {
	"Customer": [
		{
			"fieldname": "custom_active_ar_case",
			"fieldtype": "Link",
			"label": "Active AR Case",
			"options": "AR Case",
			"read_only": 1,
			"insert_after": "custom_hold_since",
		},
	],
	"Sales Order": [
		{
			"fieldname": "custom_ar_case",
			"fieldtype": "Link",
			"label": "AR Case",
			"options": "AR Case",
			"read_only": 1,
			"insert_after": "custom_workout_paydown_received",
		},
	],
	"Sales Invoice": [
		{
			"fieldname": "custom_ar_case",
			"fieldtype": "Link",
			"label": "AR Case",
			"options": "AR Case",
			"read_only": 1,
			"insert_after": "custom_finance_charge_applied_upto",
		},
	],
	"Payment Entry": [
		{
			"fieldname": "custom_ar_case",
			"fieldtype": "Link",
			"label": "AR Case",
			"options": "AR Case",
			"depends_on": "eval:['Plan','Workout Paydown'].includes(doc.custom_ledger)",
			"mandatory_depends_on": "eval:['Plan','Workout Paydown'].includes(doc.custom_ledger)",
			"insert_after": "custom_against_sales_order",
		},
		{
			"fieldname": "custom_installment",
			"fieldtype": "Data",
			"label": "Installment Row",
			"depends_on": "eval:doc.custom_ledger=='Plan'",
			"description": "The AR Case Installment row this receipt settles.",
			"insert_after": "custom_ar_case",
		},
	],
}


def install_phase_1_fields():
	create_custom_fields(PHASE_1_FIELDS, update=True)


def install_phase_4_fields():
	create_custom_fields(PHASE_4_FIELDS, update=True)


def install_exemption_fields():
	"""Re-apply the Customer block so the exemption fields and the widened
	credit-status options land on an already-migrated site."""
	create_custom_fields({"Customer": CUSTOMER_FIELDS}, update=True)


def install_phase_2_fields():
	create_custom_fields(PHASE_2_FIELDS, update=True)


def install_phase_3_fields():
	create_custom_fields(PHASE_3_FIELDS, update=True)
