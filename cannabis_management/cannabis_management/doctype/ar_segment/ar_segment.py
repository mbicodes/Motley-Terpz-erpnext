"""Segments the Categorized AR page files accounts under.

One record per segment. The record's **name is the segment text**
(``autoname: field:segment_name``), because that text is what gets written to
``Customer.custom_ar_legacy_segment`` - so the dropdown, the stored value and
this list are all the same string.

Adding a record is all it takes for a segment to appear on the page and in the
Customer form's own Select field, whose options are re-synced from here on every
change. Same arrangement as [AR Recon Status].
"""

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
        # A segment is a plain Select value, not a link, so customers already
        # filed under it keep the text. Disable rather than delete if the page
        # should stop offering it but the history should stay readable.
        self._sync(exclude=self.name)

    def _sync(self, exclude=None):
        from cannabis_management.cannabis_management.page.ar_legacy.ar_legacy import (
            sync_segment_field_options,
        )

        sync_segment_field_options(exclude=exclude)
