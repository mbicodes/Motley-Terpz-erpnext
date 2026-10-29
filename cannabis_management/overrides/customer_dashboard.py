from frappe import _

CREDIT_SECTION = "Credit & AR"

CREDIT_ITEMS = ["Credit Application", "AR Case"]


def get_data(data):
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
