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
        super().on_submit()

        notes = {row.delivery_note for row in self.items if row.get("delivery_note")}
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
        super().on_cancel()
        move_back_to_delivery_notes(self.name)

    def make_gl_entries(self, gl_entries=None, from_repost=False):
        if self.docstatus != 2:
            out = super().make_gl_entries(gl_entries=gl_entries, from_repost=from_repost)
            self._restore_missing_note_entries()
            from cannabis_management.api.undelivered_cogs import restore_for_invoice

            restore_for_invoice(self.name)
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
        notes = {row.delivery_note for row in self.items if row.get("delivery_note")}
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
