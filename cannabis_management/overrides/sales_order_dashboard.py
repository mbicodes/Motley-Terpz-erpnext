from frappe import _


def get_data(data):
	for section in data.get("transactions", []):
		if section.get("label") == _("Manufacturing"):
			if "Conversion Entry" not in section["items"]:
				section["items"].append("Conversion Entry")
			if "Stock Entry" not in section["items"]:
				section["items"].append("Stock Entry")
			break

	non_standard = data.setdefault("non_standard_fieldnames", {})
	non_standard["Stock Entry"] = "custom_sales_order"

	non_standard["Purchase Order"] = "inter_company_order_reference"

	return data
