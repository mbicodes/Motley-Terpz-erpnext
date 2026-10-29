import frappe
from frappe.model.document import Document


class ARReconStatus(Document):
    def validate(self):
        self.status_name = (self.status_name or "").strip()
        if not self.status_name:
            frappe.throw(frappe._("Status cannot be blank."))

    def on_update(self):
        self._sync()

    def after_insert(self):
        self._sync()

    def on_trash(self):
        self._sync(exclude=self.name)

    def _sync(self, exclude=None):
        from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
            sync_recon_status_options,
        )

        sync_recon_status_options(exclude=exclude)
