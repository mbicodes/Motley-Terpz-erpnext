import frappe

US_STATES = [
    ("Alabama", "AL"), ("Alaska", "AK"), ("Arizona", "AZ"), ("Arkansas", "AR"),
    ("California", "CA"), ("Colorado", "CO"), ("Connecticut", "CT"), ("Delaware", "DE"),
    ("Florida", "FL"), ("Georgia", "GA"), ("Hawaii", "HI"), ("Idaho", "ID"),
    ("Illinois", "IL"), ("Indiana", "IN"), ("Iowa", "IA"), ("Kansas", "KS"),
    ("Kentucky", "KY"), ("Louisiana", "LA"), ("Maine", "ME"), ("Maryland", "MD"),
    ("Massachusetts", "MA"), ("Michigan", "MI"), ("Minnesota", "MN"), ("Mississippi", "MS"),
    ("Missouri", "MO"), ("Montana", "MT"), ("Nebraska", "NE"), ("Nevada", "NV"),
    ("New Hampshire", "NH"), ("New Jersey", "NJ"), ("New Mexico", "NM"), ("New York", "NY"),
    ("North Carolina", "NC"), ("North Dakota", "ND"), ("Ohio", "OH"), ("Oklahoma", "OK"),
    ("Oregon", "OR"), ("Pennsylvania", "PA"), ("Rhode Island", "RI"), ("South Carolina", "SC"),
    ("South Dakota", "SD"), ("Tennessee", "TN"), ("Texas", "TX"), ("Utah", "UT"),
    ("Vermont", "VT"), ("Virginia", "VA"), ("Washington", "WA"), ("West Virginia", "WV"),
    ("Wisconsin", "WI"), ("Wyoming", "WY"), ("District of Columbia", "DC"),
]


def execute():
    from cannabis_management.api.crm_account_enhancements import install_crm_account_fields

    col_type = frappe.db.sql(
        """SELECT DATA_TYPE FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tabCRM Lead'
             AND COLUMN_NAME = 'custom_license_number'"""
    )
    if col_type and col_type[0][0] in ("varchar", "text", "longtext"):
        frappe.db.sql(
            r"""UPDATE `tabCRM Lead`
                SET custom_license_number = '0'
                WHERE custom_license_number IS NULL
                  OR custom_license_number NOT REGEXP '^[0-9]+(\.[0-9]+)?$'"""
        )
        frappe.db.commit()

    install_crm_account_fields()

    for state_name, abbr in US_STATES:
        if not frappe.db.exists("State", state_name):
            frappe.get_doc({
                "doctype": "State",
                "state_name": state_name,
                "abbreviation": abbr,
            }).insert(ignore_permissions=True)
    frappe.db.commit()
