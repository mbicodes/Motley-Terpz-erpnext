import frappe

@frappe.whitelist(allow_guest=True)
def get_item_groups():
	groups = frappe.db.sql("""
		SELECT 
			ig.name,
			COUNT(i.name) as item_count
		FROM `tabItem Group` ig
		INNER JOIN `tabItem` i ON (i.item_group = ig.name OR (ig.name = 'Fresh Frozen' AND i.item_group IN ('Fresh Frozen', 'Fresh Frozen - BHO', 'Fresh Frozen - SHO', 'Fresh Frozen Untested', 'Fresh Frozen - To Be Determined'))) 
            AND i.disabled = 0 
            AND i.custom_show_in_dashboard = 1
		WHERE ig.is_group = 0
          AND ig.custom_show_in_inventory_dashboard = 1
		GROUP BY ig.name
		ORDER BY ig.name
	""", as_dict=True)

	return groups
