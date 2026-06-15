import frappe

TERMS = [
    {
        "template_name": "NET7",
        "rows": [
            {"invoice_portion": 100, "credit_days": 7,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "Payment after 7 Days"}
        ]
    },
    {
        "template_name": "NET15",
        "rows": [
            {"invoice_portion": 100, "credit_days": 15,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "Payment after 15 Days"}
        ]
    },
    {
        "template_name": "NET30",
        "rows": [
            {"invoice_portion": 100, "credit_days": 30,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "Payment after 30 Days"}
        ]
    },
    {
        "template_name": "50% down NET15",
        "rows": [
            {"invoice_portion": 50, "credit_days": 0,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "50% down payment on invoice date"},
            {"invoice_portion": 50, "credit_days": 15,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "Balance due 15 days after invoice"}
        ]
    },
    {
        "template_name": "50% down NET30",
        "rows": [
            {"invoice_portion": 50, "credit_days": 0,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "50% down payment on invoice date"},
            {"invoice_portion": 50, "credit_days": 30,
             "due_date_based_on": "Day(s) after invoice date",
             "description": "Balance due 30 days after invoice"}
        ]
    },
]


def execute():
    for t in TERMS:
        if frappe.db.exists("Payment Terms Template", {"template_name": t["template_name"]}):
            print(f"  [skip] {t['template_name']} already exists")
            continue
        doc = frappe.new_doc("Payment Terms Template")
        doc.template_name = t["template_name"]
        for r in t["rows"]:
            doc.append("terms", r)
        doc.insert(ignore_permissions=True)
        print(f"  [ok] created: {t['template_name']}")
    frappe.db.commit()
    print("Done.")
