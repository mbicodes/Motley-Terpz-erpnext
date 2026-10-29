import frappe
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote

from cannabis_management.overrides.si_cogs_alignment import (
    ORIGIN_NO_FIELD,
    ORIGIN_TYPE_FIELD,
    delete_origin_rows,
    get_linked_sales_invoice,
    invoice_voucher_subtype,
)
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMDeliveryNote(DeliveryNote):
    def get_gl_entries(self, warehouse_account=None, default_expense_account=None, default_cost_center=None):
        gl_entries = super().get_gl_entries(
            warehouse_account=warehouse_account,
            default_expense_account=default_expense_account,
            default_cost_center=default_cost_center,
        )
        return apply_item_group_mapping(self, gl_entries, warehouse_account)

    def _aligned_sales_invoice(self):
        if not hasattr(self, "_cm_aligned_si"):
            self._cm_aligned_si = get_linked_sales_invoice(self)
        return self._cm_aligned_si

    def get_gl_dict(self, args, account_currency=None, item=None):
        gl_dict = super().get_gl_dict(args, account_currency=account_currency, item=item)

        si = self._aligned_sales_invoice()
        if not si:
            return gl_dict

        from erpnext.accounts.utils import get_fiscal_year

        gl_dict.update(
            {
                "posting_date": si.posting_date,
                "fiscal_year": get_fiscal_year(si.posting_date, company=self.company)[0],
                "voucher_type": "Sales Invoice",
                "voucher_no": si.name,
                "voucher_subtype": invoice_voucher_subtype(si.name),
                ORIGIN_TYPE_FIELD: self.doctype,
                ORIGIN_NO_FIELD: self.name,
            }
        )
        return gl_dict

    def make_gl_entries(self, gl_entries=None, from_repost=False, via_landed_cost_voucher=False):
        if self.docstatus == 2:
            reverse_origin_entries(self.doctype, self.name)
        elif from_repost:
            delete_origin_rows(self.doctype, self.name)

        return super().make_gl_entries(
            gl_entries=gl_entries,
            from_repost=from_repost,
            via_landed_cost_voucher=via_landed_cost_voucher,
        )

    def make_gl_entries_on_cancel(self, from_repost=False):
        has_origin_rows = frappe.get_all(
            "GL Entry",
            filters={
                ORIGIN_TYPE_FIELD: self.doctype,
                ORIGIN_NO_FIELD: self.name,
                "is_cancelled": 0,
            },
            pluck="name",
            limit=1,
        )
        if not has_origin_rows:
            return super().make_gl_entries_on_cancel(from_repost=from_repost)

        if not from_repost:
            from erpnext.accounts.utils import cancel_exchange_gain_loss_journal

            cancel_exchange_gain_loss_journal(frappe._dict(doctype=self.doctype, name=self.name))
        reverse_origin_entries(self.doctype, self.name)


def reverse_origin_entries(origin_type, origin_no):
    from erpnext.accounts.general_ledger import make_reverse_gl_entries

    rows = frappe.db.sql(
        """
        SELECT * FROM `tabGL Entry`
        WHERE `{otype}` = %s AND `{ono}` = %s AND is_cancelled = 0
        FOR UPDATE
        """.format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
        (origin_type, origin_no),
        as_dict=True,
    )
    if rows:
        make_reverse_gl_entries(gl_entries=rows)


@frappe.whitelist()
def get_accounting_ledger_route(delivery_note):
    doc = frappe.get_doc("Delivery Note", delivery_note)
    doc.check_permission("read")

    rows = frappe.db.sql(
        """
        SELECT voucher_no, MIN(posting_date) AS from_date, MAX(posting_date) AS to_date
        FROM `tabGL Entry`
        WHERE (voucher_type = 'Delivery Note' AND voucher_no = %(dn)s)
            OR (`{otype}` = 'Delivery Note' AND `{ono}` = %(dn)s)
        GROUP BY voucher_no
        ORDER BY voucher_no = %(dn)s DESC, MIN(posting_date)
        LIMIT 1
        """.format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
        {"dn": doc.name},
        as_dict=True,
    )
    if rows:
        return rows[0]
    return {"voucher_no": doc.name, "from_date": doc.posting_date, "to_date": doc.posting_date}
