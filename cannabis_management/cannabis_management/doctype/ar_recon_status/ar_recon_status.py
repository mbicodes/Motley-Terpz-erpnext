"""Reconciliation statuses offered by the AR Dashboard.

One record per status. The record's **name is the status text** itself
(``autoname: field:status_name``), because that text is what gets written to
``Customer.custom_reconciliation_status`` - so the dropdown, the stored value
and this list are all the same string and nothing needs mapping.

Adding a record is all it takes for a new status to appear in the dashboard
dropdown and in the Customer form's own Select field; the Select's options are
re-synced from here whenever a status is added, changed or removed.
"""

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
        # Customers already set to this status keep the text they have - it is a
        # plain Select value, not a link - so removing a status only takes it out
        # of the dropdown. Disable rather than delete if that matters.
        self._sync(exclude=self.name)

    def _sync(self, exclude=None):
        from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
            sync_recon_status_options,
        )

        sync_recon_status_options(exclude=exclude)
