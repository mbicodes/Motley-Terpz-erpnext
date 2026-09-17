import frappe

# Plain NET terms before their "50% down" variants, each group sorted by day
# count — the order the client asked the Payment Terms dropdown to list in.
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

# Never offered on this form, regardless of what's in Payment Terms Template.
APPROVED_TERMS_EXCLUDE = {"COD", "PAYMENT SCHEDULE BREAKDOWN"}


def get_context(context):
	"""Context for the public Credit Agreement web form."""
	context.no_cache = 1
	# Keep this client-facing page's title clean — skip the sitewide "MT -" prefix.
	context.title_prefix = None

	# Web forms turn every Link field into an "Autocomplete" backed by a
	# static list of every record name (see WebForm.load_form_data ->
	# get_link_options, which fetches with no filters or ordering at all)
	# baked into context.web_form_doc.web_form_fields before this hook
	# runs. There's no per-field filter/order hook for that, so the only
	# way to control what shows (and in what order) is to rewrite the
	# already-built options string here.
	_set_link_options(context, "sales_person", _sales_person_rep_names())
	_set_link_options(context, "approved_terms", _approved_terms_names())


def _sales_person_rep_names():
	"""Actual Sales Person reps — "group" org-tree nodes excluded."""
	return frappe.get_all("Sales Person", filters={"is_group": 0}, pluck="name")


def _approved_terms_names():
	existing = set(frappe.get_all("Payment Terms Template", pluck="name")) - APPROVED_TERMS_EXCLUDE
	ordered = [name for name in APPROVED_TERMS_ORDER if name in existing]
	# Any term added later that isn't in our explicit order (and isn't
	# excluded above) still shows up, just tacked on at the end, instead of
	# silently vanishing from the list.
	ordered += sorted(existing - set(ordered))
	return ordered


def _set_link_options(context, fieldname, values):
	for field in context.web_form_doc.web_form_fields:
		if field.get("fieldname") == fieldname:
			field.options = "\n".join(values)
			break
