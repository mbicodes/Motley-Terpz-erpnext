import frappe
from frappe.model.document import Document


class ARSegment(Document):
    def validate(self):
        self.segment_name = (self.segment_name or "").strip()
        if not self.segment_name:
            frappe.throw(frappe._("Segment cannot be blank."))

    def on_update(self):
        self._sync()

    def after_insert(self):
        self._sync()

    def on_trash(self):
        self._sync(exclude=self.name)

    def _sync(self, exclude=None):
        from cannabis_management.cannabis_management.page.ar_legacy.ar_legacy import (
            sync_segment_field_options,
        )

        sync_segment_field_options(exclude=exclude)
