from frappe import _


def get_data(data):
	# Add Conversion Entry and its resulting Stock Entries to the Manufacturing group
	for section in data.get("transactions", []):
		if section.get("label") == _("Manufacturing"):
			if "Conversion Entry" not in section["items"]:
				section["items"].append("Conversion Entry")
			if "Stock Entry" not in section["items"]:
				section["items"].append("Stock Entry")
			break

	# Tell Frappe to look up Stock Entry via custom_sales_order instead of sales_order
	non_standard = data.setdefault("non_standard_fieldnames", {})
	non_standard["Stock Entry"] = "custom_sales_order"

	return data
