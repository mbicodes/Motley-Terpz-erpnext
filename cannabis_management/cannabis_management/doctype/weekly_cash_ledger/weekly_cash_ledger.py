import frappe
from frappe.model.document import Document
from frappe.utils import flt

# Keep in sync with the category Select options on the child doctypes.
CATEGORIES = [
    "Frozen", "Rosin/VRR", "Edibles", "Packaged Goods", "White Label",
    "Bubble/Static", "Pre-Rolls", "Other Extracts", "Tolling", "Other",
]


class WeeklyCashLedger(Document):
    def before_insert(self):
        # Start every new week with a full target grid, like the sheet's
        # fixed weekly goals. Reps then fill in the numbers.
        if not self.targets:
            for category in CATEGORIES:
                self.append("targets", {"category": category})

    def validate(self):
        self.set_title()
        self.compute_summaries()

    def set_title(self):
        parts = [f"Week of {frappe.utils.formatdate(self.week_of, 'MMM dd, yyyy')}"]
        if self.sales_person:
            parts.append(self.sales_person)
        self.ledger_title = " — ".join(parts)

    def compute_summaries(self):
        def money(line):
            """A line's dollar value: collected amount, else the expected amount."""
            return flt(line.amount) or flt(line.expected_amount)

        collected = [l for l in self.lines if l.status == "Collected"]
        expected = [l for l in self.lines if l.status == "Expected this week"]

        def split(rows):
            total = sum(money(l) for l in rows)
            cash = sum(money(l) for l in rows if l.method == "Cash")
            bank = sum(money(l) for l in rows if l.method == "Bank")
            return total, cash, bank

        self.collected_total, self.collected_cash, self.collected_bank = split(collected)
        self.expected_total, self.expected_cash, self.expected_bank = split(expected)
        self.coming_in_total = self.collected_total + self.expected_total
        self.coming_in_cash = self.collected_cash + self.expected_cash
        self.coming_in_bank = self.collected_bank + self.expected_bank

        sales = [l for l in self.lines if l.entry_type == "Sales"]
        self.sales_written_total = sum(money(l) for l in sales)
        self.sales_cod = sum(money(l) for l in sales if l.terms == "COD")
        self.sales_terms = sum(money(l) for l in sales if l.terms == "Terms")

        ar = [l for l in self.lines if l.entry_type == "AR"]
        self.ar_total = sum(money(l) for l in ar)
        self.ar_collected = sum(money(l) for l in ar if l.status == "Collected")
        self.ar_expected = sum(money(l) for l in ar if l.status == "Expected this week")

        outbound = [l for l in self.lines if l.direction == "Outbound"]
        inbound = [l for l in self.lines if l.direction == "Inbound"]
        self.outbound_value = sum(money(l) for l in outbound)
        self.outbound_orders = len(outbound)
        self.inbound_value = sum(money(l) for l in inbound)
        self.inbound_orders = len(inbound)

        # Per-category actuals (new sales only, matching the sheet)
        by_category = {}
        for l in sales:
            if l.category:
                by_category[l.category] = by_category.get(l.category, 0.0) + money(l)
        for t in self.targets:
            t.actual_amount = by_category.get(t.category, 0.0)
        self.sales_target_total = sum(flt(t.target_amount) for t in self.targets)
