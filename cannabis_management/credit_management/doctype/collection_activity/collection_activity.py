import frappe
from frappe.model.document import Document


class CollectionActivity(Document):
    pass


def latest_for_customer(customer):
    rows = frappe.get_all(
        "Collection Activity",
        filters={"customer": customer},
        fields=["activity_date", "activity_type", "promise_to_pay_date", "promise_amount",
                "next_action", "next_action_date"],
        order_by="activity_date desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None
