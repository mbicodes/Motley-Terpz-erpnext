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

	# The inter-company Purchase Order this order raised. Found through the
	# Purchase Order's own inter_company_order_reference rather than a field on
	# the Sales Order, so the link shows even on orders raised before the
	# reverse reference was being filled in.
	# Purchase Order is already listed under Purchasing, linked by core through
	# the drop-ship field on this order's items. Adding it to a second group
	# would show it twice, so only the lookup is extended: when that internal
	# link finds nothing, Frappe falls back to non_standard_fieldnames (see
	# frappe/desk/notifications.py get_open_count), which finds the
	# inter-company Purchase Order raised from this order instead.
	non_standard["Purchase Order"] = "inter_company_order_reference"

	return data
