from frappe import _

CREDIT_SECTION = "Credit & AR"


def get_data(data):
	"""Surface the customer's Credit Applications on the Customer Connections tab.

	Credit Application links to Customer through a plain ``customer`` field, which
	is already the Customer dashboard's default fieldname, so no
	non_standard_fieldnames entry is needed.

	Added as its own group rather than folded into Payments: an application is
	the paperwork behind the line, not a transaction against it, and the group
	gives AR Case and anything else from this module somewhere obvious to go.
	"""
	for section in data.get("transactions", []):
		if section.get("label") == _(CREDIT_SECTION):
			if "Credit Application" not in section["items"]:
				section["items"].append("Credit Application")
			return data

	data.setdefault("transactions", []).append(
		{"label": _(CREDIT_SECTION), "items": ["Credit Application"]}
	)
	return data
