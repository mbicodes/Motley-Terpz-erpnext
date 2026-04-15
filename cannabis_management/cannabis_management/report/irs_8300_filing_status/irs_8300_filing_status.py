import frappe

def execute(filters=None):
    columns = [
        {"label": "Payment Entry", "fieldname": "payment_entry", "fieldtype": "Link",
         "options": "Payment Entry", "width": 180},
        {"label": "Customer", "fieldname": "customer", "width": 180},
        {"label": "Payment Date", "fieldname": "payment_date",
         "fieldtype": "Date", "width": 120},
        {"label": "Cash Amount", "fieldname": "cash_amount",
         "fieldtype": "Currency", "width": 130},
        {"label": "Filing Deadline", "fieldname": "filing_deadline",
         "fieldtype": "Date", "width": 120},
        {"label": "Days Left", "fieldname": "days_left",
         "fieldtype": "Int", "width": 90},
        {"label": "8300 Log", "fieldname": "log_name", "fieldtype": "Link",
         "options": "IRS Form 8300 Log", "width": 160},
        {"label": "Filing Status", "fieldname": "filing_status", "width": 140},
        {"label": "Attachment", "fieldname": "has_attachment",
         "fieldtype": "Check", "width": 100},
    ]

    conditions = "WHERE pe.paid_amount > 10000"

    if filters:
        if filters.get("customer"):
            conditions += " AND pe.party = %(customer)s"
        if filters.get("from_date"):
            conditions += " AND pe.posting_date >= %(from_date)s"
        if filters.get("to_date"):
            conditions += " AND pe.posting_date <= %(to_date)s"
        if filters.get("filing_status"):
            conditions += " AND computed_status = %(filing_status)s"

    data = frappe.db.sql(f"""
        SELECT
            pe.name                                         AS payment_entry,
            pe.party                                        AS customer,
            pe.posting_date                                 AS payment_date,
            pe.paid_amount                                  AS cash_amount,
            DATE_ADD(pe.posting_date, INTERVAL 15 DAY)      AS filing_deadline,
            DATEDIFF(
                DATE_ADD(pe.posting_date, INTERVAL 15 DAY),
                CURDATE()
            )                                               AS days_left,
            ref.parent                                      AS log_name,
            IF(f.name IS NOT NULL, 1, 0)                    AS has_attachment,
            CASE
                WHEN f.name IS NOT NULL
                    THEN 'Reported'
                WHEN log.filing_status IN ('Filed - E-File', 'Filed - Paper')
                    THEN log.filing_status
                WHEN DATEDIFF(DATE_ADD(pe.posting_date, INTERVAL 15 DAY), CURDATE()) < 0
                    THEN 'Overdue'
                ELSE 'Pending'
            END                                             AS filing_status

        FROM `tabPayment Entry` pe

        LEFT JOIN `tabIRS 8300 Payment Reference` ref
            ON ref.payment_entry = pe.name

        LEFT JOIN `tabIRS Form 8300 Log` log
            ON log.name = ref.parent

        LEFT JOIN `tabFile` f
            ON f.attached_to_doctype = 'Payment Entry'
            AND f.attached_to_name = pe.name

        {conditions}
          AND pe.party_type = 'Customer'
          AND pe.docstatus = 1
          AND pe.mode_of_payment IN (
              SELECT name FROM `tabMode of Payment` WHERE type = 'Cash'
          )

        ORDER BY pe.posting_date ASC
    """, filters or {}, as_dict=True)

    return columns, data