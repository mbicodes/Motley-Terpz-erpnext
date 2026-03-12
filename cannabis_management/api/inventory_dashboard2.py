import frappe

@frappe.whitelist(allow_guest=True)
def get_item_groups():
	"""Fetch all item groups - accessible without login"""
	groups = frappe.db.sql("""
		SELECT 
			ig.name,
			COUNT(i.name) as item_count
		FROM `tabItem Group` ig
		LEFT JOIN `tabItem` i ON i.item_group = ig.name AND i.disabled = 0
		WHERE ig.is_group = 0 and ig.custom_show_in_dashboard = 1
		GROUP BY ig.name
		ORDER BY ig.name
	""", as_dict=True)
	
	return groups