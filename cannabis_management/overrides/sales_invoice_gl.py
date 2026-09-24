import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from cannabis_management.overrides.si_cogs_alignment import (
    ORIGIN_NO_FIELD,
    get_linked_sales_invoice,
    move_back_to_delivery_notes,
    move_to_invoice,
)


class CMSalesInvoice(SalesInvoice):
    def on_submit(self):
        """Pull in the stock GL of notes delivered before this invoice.

        Those notes posted on their own date because there was no invoice yet.
        Each is moved only if this is the single invoice it resolves to, which
        also covers notes linked to this invoice only through the Sales Order.
        """
        super().on_submit()

        notes = {row.delivery_note for row in self.items if row.get("delivery_note")}
        # Billed off the Sales Order: the note is only reachable through it.
        lines = [row.so_detail for row in self.items if row.get("so_detail")]
        if lines:
            notes.update(
                frappe.get_all(
                    "Delivery Note Item",
                    filters={"so_detail": ("in", lines), "docstatus": 1},
                    pluck="parent",
                )
            )
        for dn in sorted(notes):
            note = frappe.get_doc("Delivery Note", dn)
            if note.docstatus != 1:
                continue
            si = get_linked_sales_invoice(note)
            if si and si.name == self.name:
                move_to_invoice(dn, si)

    def on_cancel(self):
        """Hand borrowed notes' stock GL back to the notes themselves.

        The notes are unbilled again, so their COGS goes back to where core
        posts it. A replacement invoice pulls it in again on submit.
        """
        super().on_cancel()
        move_back_to_delivery_notes(self.name)

    def make_gl_entries(self, gl_entries=None, from_repost=False):
        """Cancel only the rows this invoice actually posted.

        Delivery Note stock entries are filed under this invoice's number (see
        si_cogs_alignment), and core's cancel reverses *everything* carrying
        that voucher_no. That would unbook a delivered note's COGS while the
        stock stayed out of the warehouse, and leave the note with nothing to
        reverse when it is cancelled in turn.

        Rows the invoice posted itself have no origin stamp, so select those
        explicitly and hand them to the reversal rather than letting it query
        by voucher number.
        """
        if self.docstatus != 2:
            out = super().make_gl_entries(gl_entries=gl_entries, from_repost=from_repost)
            self._restore_missing_note_entries()
            return out

        from erpnext.accounts.general_ledger import make_reverse_gl_entries

        own_rows = frappe.db.sql(
            """
            SELECT * FROM `tabGL Entry`
            WHERE voucher_type = %s AND voucher_no = %s AND is_cancelled = 0
              AND IFNULL(`{origin}`, '') = ''
            FOR UPDATE
            """.format(origin=ORIGIN_NO_FIELD),
            (self.doctype, self.name),
            as_dict=True,
        )

        if own_rows:
            make_reverse_gl_entries(gl_entries=own_rows)

    def _restore_missing_note_entries(self):
        """Rebuild borrowed rows a repost of this invoice has deleted.

        Repost Accounting Ledger with "delete cancelled entries" deletes every
        row under this invoice's number, the notes' included, and then posts
        only the invoice's own. A note left with no live GL at all is reposted,
        which files its entries back under this invoice.
        """
        notes = {row.delivery_note for row in self.items if row.get("delivery_note")}
        # Billed-first notes carry the link on their own rows instead.
        notes.update(
            frappe.get_all(
                "Delivery Note Item",
                filters={"against_sales_invoice": self.name, "docstatus": 1},
                pluck="parent",
            )
        )
        lines = [row.so_detail for row in self.items if row.get("so_detail")]
        if lines:
            notes.update(
                frappe.get_all(
                    "Delivery Note Item",
                    filters={"so_detail": ("in", lines), "docstatus": 1},
                    pluck="parent",
                )
            )
        for dn in sorted(notes):
            if frappe.db.get_value("Delivery Note", dn, "docstatus") != 1:
                continue
            live = frappe.db.sql(
                """SELECT 1 FROM `tabGL Entry` WHERE is_cancelled = 0
                AND ((voucher_type = 'Delivery Note' AND voucher_no = %(dn)s)
                     OR `{ono}` = %(dn)s) LIMIT 1""".format(ono=ORIGIN_NO_FIELD),
                {"dn": dn},
            )
            if live:
                continue
            note = frappe.get_doc("Delivery Note", dn)
            si = get_linked_sales_invoice(note)
            if si and si.name == self.name:
                note.make_gl_entries(from_repost=True)
