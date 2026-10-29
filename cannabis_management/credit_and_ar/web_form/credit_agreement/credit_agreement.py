import frappe

APPROVED_TERMS_ORDER = [
	"NET7",
	"NET15",
	"NET21",
	"NET30",
	"50% down NET7",
	"50% down NET15",
	"50% down NET21",
	"50% down NET30",
]

APPROVED_TERMS_EXCLUDE = {"COD", "PAYMENT SCHEDULE BREAKDOWN"}


def get_context(context):
	context.no_cache = 1
	context.title_prefix = None

	_set_link_options(context, "sales_person", _sales_person_rep_names())
	_set_link_options(context, "approved_terms", _approved_terms_names())


def _sales_person_rep_names():
	return frappe.get_all("Sales Person", filters={"is_group": 0}, pluck="name")


def _approved_terms_names():
	existing = set(frappe.get_all("Payment Terms Template", pluck="name")) - APPROVED_TERMS_EXCLUDE
	ordered = [name for name in APPROVED_TERMS_ORDER if name in existing]
	ordered += sorted(existing - set(ordered))
	return ordered


def _set_link_options(context, fieldname, values):
	for field in context.web_form_doc.web_form_fields:
		if field.get("fieldname") == fieldname:
			field.options = "\n".join(values)
			break
