import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate

LEDGER = "Referral Commission Ledger"
STATEMENT = "Referral Commission Statement"


class ReferralCommissionStatement(Document):
    def validate(self):
        self.set_period_dates()
        dup = frappe.db.exists(
            STATEMENT,
            {
                "referral_partner": self.referral_partner,
                "company": self.company,
                "period": self.period,
                "docstatus": ["!=", 2],
                "name": ["!=", self.name],
            },
        )
        if dup:
            frappe.throw(
                _("Statement {0} already exists for {1}, {2} and period {3}. Only one active statement is allowed per partner, company and period.").format(
                    dup, self.referral_partner, self.company, self.period
                )
            )
        if flt(self.adjustment_amount) and not self.adjustment_reason:
            frappe.throw(_("Please enter a reason for the manual adjustment."))
        self.calculate()

    def after_insert(self):
        # Amend copies the cancelled statement's table, but cancel released its ledger lines:
        # relink them now, or the copy would be paid and the next run would pay the lines again.
        if self.amended_from:
            self.flags.ignore_permissions = True
            self.rebuild()

    def set_period_dates(self):
        try:
            y, m = [int(x) for x in self.period.split("-")]
            first = getdate(f"{y:04d}-{m:02d}-01")
        except Exception:
            frappe.throw(_("Period must be in the format YYYY-MM."))
        self.period_start = first
        self.period_end = get_last_day(first)
        self.due_date = add_days(self.period_end, 30)

    def calculate(self):
        self.total_received = sum(flt(r.amount_received) for r in self.lines)
        self.total_commission = sum(flt(r.commission_amount) for r in self.lines)
        self.net_payable = flt(self.total_commission) + flt(self.carry_forward_in) + flt(self.adjustment_amount)

    # ------------------------------------------------------------------ build
    @frappe.whitelist()
    def rebuild(self):
        """(Re)link the open ledger lines of this partner and company and rebuild the table. Drafts only."""
        if not self.flags.ignore_permissions:
            self.check_permission("write")
        if self.docstatus != 0:
            frappe.throw(_("Only a Draft statement can be rebuilt."))
        release_lines(self.name)
        lines = frappe.get_all(
            LEDGER,
            filters={
                "referral_partner": self.referral_partner,
                "company": self.company,
                "statement": ["is", "not set"],
                "period": ["<=", self.period],
            },
            fields=["name", "customer", "partner_referral", "month_no", "rate", "amount_received", "commission_amount", "is_reversal"],
            order_by="posting_date asc, creation asc",
        )
        groups = {}
        for l in lines:
            g = groups.setdefault(l.customer, {"lines": [], "ref": l.partner_referral})
            g["lines"].append(l)
        self.set("lines", [])
        for customer, g in groups.items():
            ls = g["lines"]
            months = sorted(x.month_no for x in ls)
            top = max(ls, key=lambda x: x.month_no)
            lo, hi = months[0], months[-1]
            self.append(
                "lines",
                {
                    "customer": customer,
                    "partner_referral": g["ref"],
                    "month_no_range": str(lo) if lo == hi else f"{lo}–{hi}",
                    "rate": top.rate,
                    "payments_count": len([x for x in ls if not x.is_reversal]),
                    "amount_received": sum(flt(x.amount_received) for x in ls),
                    "commission_amount": sum(flt(x.commission_amount) for x in ls),
                },
            )
        for l in lines:
            frappe.db.set_value(LEDGER, l.name, "statement", self.name, update_modified=False)
        # carry-forward from earlier statements that were not paid out
        cf = frappe.get_all(
            STATEMENT,
            filters={
                "referral_partner": self.referral_partner,
                "company": self.company,
                "docstatus": 1,
                "status": "Carried Forward",
                "carried_to": ["is", "not set"],
                "name": ["!=", self.name],
            },
            fields=["name", "net_payable"],
        )
        self.carry_forward_in = sum(flt(c.net_payable) for c in cf)
        for c in cf:
            frappe.db.set_value(STATEMENT, c.name, "carried_to", self.name, update_modified=False)
        self.calculate()
        self.flags.ignore_permissions = True
        self.save()

    # ------------------------------------------------------------------ approve (submit)
    def on_submit(self):
        from motley_referral import notifications
        from motley_referral.engine import settings

        s = settings()
        if flt(self.net_payable) < flt(s.minimum_payout) or flt(self.net_payable) <= 0:
            self.db_set("status", "Carried Forward")
            frappe.msgprint(
                _("Net payable {0} is below the minimum payout of {1}. The amount is carried forward to the next statement.").format(
                    frappe.format_value(self.net_payable, {"fieldtype": "Currency"}),
                    frappe.format_value(s.minimum_payout, {"fieldtype": "Currency"}),
                ),
                indicator="orange",
                alert=True,
            )
            return
        pi = self.make_purchase_invoice()
        self.db_set({"status": "Approved", "purchase_invoice": pi})
        notifications.notify("statement_approved", statement=self)

    def make_purchase_invoice(self):
        from motley_referral.engine import settings

        partner = frappe.get_doc("Referral Partner", self.referral_partner)
        if not partner.supplier:
            frappe.throw(_("Referral Partner {0} has no Supplier. Activate the partner first.").format(partner.name))
        account = None
        for r in settings().get("eligible_companies") or []:
            if r.company == self.company:
                account = r.commission_expense_account
        if not account:
            frappe.throw(_("Set the commission expense account for {0} in Referral Settings.").format(self.company))
        today = getdate(nowdate())
        pi = frappe.new_doc("Purchase Invoice")
        pi.update(
            {
                "supplier": partner.supplier,
                "company": self.company,
                "posting_date": today,
                "bill_no": self.name,
                "bill_date": today,
                "due_date": max(getdate(self.due_date), today),
                "remarks": _("Referral commission statement {0} for {1}").format(self.name, self.period),
            }
        )
        pi.append(
            "items",
            {
                "item_name": _("Referral commission {0}").format(self.period),
                "description": _("Referral commission {0} ({1})").format(self.period, self.name),
                "qty": 1,
                "uom": "Nos",
                "rate": flt(self.net_payable),
                "expense_account": account,
                "cost_center": frappe.get_cached_value("Company", self.company, "cost_center"),
            },
        )
        pi.flags.ignore_permissions = True
        pi.insert()
        pi.submit()
        return pi.name

    # ------------------------------------------------------------------ cancel
    def before_cancel(self):
        if self.status == "Paid":
            frappe.throw(_("A paid statement cannot be cancelled. Cancel the payment first."))
        carried_to = self.get("carried_to")
        if carried_to and frappe.db.get_value(STATEMENT, carried_to, "docstatus") == 1:
            frappe.throw(
                _("This balance was carried into statement {0}, which is already approved. Cancel {0} first.").format(carried_to)
            )

    def on_cancel(self):
        if self.purchase_invoice and frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus") == 1:
            pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
            pi.flags.ignore_permissions = True
            pi.cancel()
        release_lines(self.name)
        carried_to = self.get("carried_to")
        self.db_set({"status": "Cancelled", "carried_to": None})
        if carried_to:
            rebuild_draft(carried_to)  # drop this balance from the later draft's carry-forward

    def on_trash(self):
        if self.docstatus == 0:
            release_lines(self.name)



def release_lines(name):
    """Free the ledger lines and carry-forwards linked to a statement."""
    frappe.db.sql("update `tabReferral Commission Ledger` set statement=null where statement=%s", name)
    frappe.db.sql("update `tabReferral Commission Statement` set carried_to=null where carried_to=%s", name)


def rebuild_draft(name):
    """System rebuild (e.g. after a reversal): runs whatever the current user's statement rights."""
    if frappe.db.get_value(STATEMENT, name, "docstatus") == 0:
        doc = frappe.get_doc(STATEMENT, name)
        doc.flags.ignore_permissions = True
        doc.rebuild()


# ----------------------------------------------------------------------------- monthly run
def previous_period(today=None):
    first = get_first_day(getdate(today or nowdate()))
    return add_months(first, -1).strftime("%Y-%m")


def create_monthly_statements(period=None):
    """One Draft statement per partner per company for the period. Returns the list of names created."""
    from motley_referral import notifications

    period = period or previous_period()
    pairs = frappe.db.sql(
        """select distinct referral_partner, company from `tabReferral Commission Ledger`
        where (statement is null or statement = '') and period <= %s
        union
        select distinct referral_partner, company from `tabReferral Commission Statement`
        where docstatus = 1 and status = 'Carried Forward' and (carried_to is null or carried_to = '')
        and period < %s""",
        (period, period),
        as_dict=True,
    )
    created = []
    for p in pairs:
        if frappe.db.exists(
            STATEMENT,
            {"referral_partner": p.referral_partner, "company": p.company, "period": period, "docstatus": ["!=", 2]},
        ):
            continue
        doc = frappe.new_doc(STATEMENT)
        doc.update({"referral_partner": p.referral_partner, "company": p.company, "period": period})
        doc.flags.ignore_permissions = True
        doc.insert()
        doc.rebuild()
        created.append(doc.name)
    if created:
        notifications.notify("run_ready", period=period, count=len(created))
    return created


@frappe.whitelist()
def run_now(period=None):
    frappe.only_for(("Accounts Manager", "Referral Manager", "System Manager"))
    return len(create_monthly_statements(period))


# ----------------------------------------------------------------------------- paid hook
def on_payment_entry_submit(doc, method=None):
    from motley_referral import notifications

    for ref in doc.get("references") or []:
        if ref.reference_doctype != "Purchase Invoice":
            continue
        st = frappe.db.get_value(STATEMENT, {"purchase_invoice": ref.reference_name, "docstatus": 1}, "name")
        if not st:
            continue
        if flt(frappe.db.get_value("Purchase Invoice", ref.reference_name, "outstanding_amount")) > 0.005:
            continue
        statement = frappe.get_doc(STATEMENT, st)
        statement.db_set({"status": "Paid", "payment_entry": doc.name, "paid_on": doc.posting_date})
        try:
            notifications.notify("statement_paid", statement=statement, attach_pdf=True)
        except Exception:
            frappe.log_error(title="Referral Statement Paid Email", message=frappe.get_traceback())


def on_payment_entry_cancel(doc, method=None):
    for st in frappe.get_all(STATEMENT, filters={"payment_entry": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value(STATEMENT, st, {"status": "Approved", "payment_entry": None, "paid_on": None})
