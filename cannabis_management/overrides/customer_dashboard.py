from frappe import _

CREDIT_SECTION = "Credit & AR"


CREDIT_ITEMS = ["Credit Application", "AR Case"]


def get_data(data):
	"""Surface the customer's Credit Applications and AR Cases on the Customer
	Connections tab.

	Both link to Customer through a plain ``customer`` field, which is already
	the Customer dashboard's default fieldname, so no non_standard_fieldnames
	entry is needed for either.

	Added as its own group rather than folded into Payments: an application is
	the paperwork behind the line, not a transaction against it, and the group
	gives AR Case and anything else from this module somewhere obvious to go.
	"""
	for section in data.get("transactions", []):
		if section.get("label") == _(CREDIT_SECTION):
			for item in CREDIT_ITEMS:
				if item not in section["items"]:
					section["items"].append(item)
			return data

	data.setdefault("transactions", []).append(
		{"label": _(CREDIT_SECTION), "items": list(CREDIT_ITEMS)}
	)
	return data
