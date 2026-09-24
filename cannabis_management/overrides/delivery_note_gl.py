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

    # ── File the stock GL under the Sales Invoice ────────────────────────────

    def _aligned_sales_invoice(self):
        """Resolved once per submit; get_gl_dict is called once per GL row."""
        if not hasattr(self, "_cm_aligned_si"):
            self._cm_aligned_si = get_linked_sales_invoice(self)
        return self._cm_aligned_si

    def get_gl_dict(self, args, account_currency=None, item=None):
        """Restamp the entry onto the linked Sales Invoice.

        get_gl_dict is the single place core sets posting_date, fiscal_year,
        voucher_type and voucher_no, which makes it the one honest seam for
        this. Amounts and accounts are decided elsewhere and stay untouched.
        """
        gl_dict = super().get_gl_dict(args, account_currency=account_currency, item=item)

        si = self._aligned_sales_invoice()
        if not si:
            return gl_dict

        # fiscal_year has to follow the date, or the entry lands in the wrong
        # year and period-close reports disagree with the ledger.
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

    # ── Cancellation ────────────────────────────────────────────────────────

    def make_gl_entries(self, gl_entries=None, from_repost=False, via_landed_cost_voucher=False):
        """Reverse restamped rows on cancel, and clear them before a repost.

        Core reverses by (voucher_type, voucher_no) = (Delivery Note, name).
        Restamped rows are filed under the Sales Invoice, so core finds nothing
        and the stock goes back while the COGS stays booked. Reverse those by
        origin first, then let core handle anything that stayed on this note.

        A valuation repost has the same blind spot: it deletes this note's GL
        by voucher and posts a fresh set, so the restamped rows would survive
        next to the new ones and the COGS would be booked twice.
        """
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
        """Core gates the reversal on GL existing under (doctype, name).

        That check fails for a restamped note, so the reversal above would
        never run. Call it directly when origin rows exist.
        """
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
    """Reverse every restamped entry the way core cancels any voucher.

    Rows are passed by name, so core flags only these as cancelled and not the
    invoice's own rows that share the voucher number. Its reversing rows are
    copies, so they keep the origin stamps too.
    """
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
