import frappe
from frappe.model.document import Document


class WorkoutTerms(Document):
    def validate(self):
        if self.status == "Active" and not self.md_approval:
            frappe.throw("Workout designation requires MD approval (Credit Exception Log).")

    def on_update(self):
        name = frappe.db.get_value("Credit Profile", {"customer": self.customer})
        if not name:
            return
        if self.status == "Active":
            frappe.db.set_value("Credit Profile", name, "status", "Workout")
        elif self.status == "Ended" and frappe.db.get_value("Credit Profile", name, "status") == "Workout":
            frappe.db.set_value("Credit Profile", name, "status", "COD")


def get_active_workout(customer):
    name = frappe.db.get_value("Workout Terms", {"customer": customer, "status": "Active"})
    return frappe.get_doc("Workout Terms", name) if name else None
