# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash-basis classification of every Bank / Cash movement of TSBC Ranch,
Motley Terpz and Master Touch Manufacturing.

One engine behind two reports, so they can never disagree:
  * Reconciled Cash Basis Profit and Loss  (per company and consolidated)
  * Cash Basis Transaction Review          (every movement and how it was read)

classify(from_date, to_date) returns one allocation per piece of every Bank /
Cash GL line posted in the window. The pieces of a line always add up to the
line, so the review reconciles to the ledgers to the cent. Matching (payroll,
intercompany) is done over all dates first, so a line is read the same way
whatever window is asked for.

How a Bank / Cash line is read
------------------------------
Pairing: a Bank / Cash line pairs with the lines on the other side of its
voucher (pro rata). When several Bank / Cash lines share a side, a line pairs
with the one opposite line of exactly its amount if there is one. The GL's
Against column is not used for this: it is plain text and keeps an account's
old name after a rename.

Each pairing is classified by the partner line:
  Income / Expense head       P&L of the company, COGS or Opex by the group
                              it sits under directly below the Expense root.
  another Bank / Cash         transfer.
  customer (Debtors)          traced through the Payment Ledger to what the
                              receipt settled: a Sales Invoice -> its income
                              heads (sales tax share is Balance Sheet); an
                              opening invoice / opening Journal -> income
                              "Customer receipts - opening invoices"; nothing
                              -> income "Customer receipts (no invoice link)".
                              Internal customers are intercompany.
  supplier (Creditors)        traced the same way to the Purchase Invoices
                              paid: expense heads count; inventory, stock
                              received not billed, assets are Balance Sheet;
                              opening bills and unallocated payments are
                              Unclassified. Internal suppliers: intercompany.
  intercompany account        matched to the mirror line in the other company
                              (opposite side, same amount, nearest date). The
                              mirror's partners decide: Bank / Cash ->
                              intercompany transfer; anything else is
                              classified for THAT company (an expense TSBC paid
                              for MTM is MTM's expense, counted once). No match:
                              Unclassified.
  Payroll Payable             matched to the payroll posting of the same amount
                              -> that wages head; else the employee named in
                              the payment reference; else "Wages paid (employee
                              not identified)" in the section every payroll
                              posting of that company uses (Opex).
  Employee Payable            Balance Sheet (funding / reimbursing an expense
                              tracker; the expenses count where the tracker
                              pays them, never twice).
  anything else               Balance Sheet.
"""

import collections
import re

import frappe
from frappe.utils import flt, getdate

COMPANIES = ("TSBC Ranch", "Motley Terpz", "Master Touch Manufacturing")
CASH_TYPES = ("Bank", "Cash")
EPS = 0.005
IC_DAYS = 10          # exact amount within this many days: a firm match
IC_WIDE_DAYS = 60     # exact amount (or within IC_CENTS) up to this: a match, noted
IC_CENTS = 0.10
IC_SHORT_DAYS = 3     # cash on both sides, amounts within IC_SHORT_RATIO: same movement
IC_SHORT_RATIO = 0.01
IC_TOGETHER_SECONDS = 900   # both sides keyed in within 15 minutes: one entry, even if a date is mistyped
IC_TWIN_RATIO = 0.10        # same-day twins whose amounts disagree by up to this share
PAYROLL_DAYS = 75

# The intercompany accounts each pair of companies keeps for each other. Any
# account of one side mirrors any account of the other: whether a company
# books against its "Receivable" or its "Payable" account for the other only
# labels the same position, and both labels are in use (TSBC debits "IC Payable
# - MTM" for MTM costs it pays as well as "IC Receivable MTM"). The direction
# must be opposite: one company's debit is the other's credit.
IC_PAIRS = (
	(("TSBC Ranch", ["IC Receivable MTM - TSBC", "IC Payable - MTM - TSBC"]),
	 ("Master Touch Manufacturing", ["IC Payable - TSBC - MTM", "IC Receivable - TSBC - MTM"])),
	(("TSBC Ranch", ["IC Payable MT - TSBC", "Inter-Company Receivable - TSBC"]),
	 ("Motley Terpz", ["IC Receivable - TSBC - MT", "Due From TSBC Ranch - MT", "Inter-Company Payable - MT",
	                   "Due To TSBC Ranch - MT"])),
	(("Master Touch Manufacturing", ["IC Payable - Motley Terpz - MTM", "Inter Company Payable MT - MTM"]),
	 ("Motley Terpz", ["IC Receivable - MTM - MT", "Inter-Company Receivable MTM - MT"])),
)
# Intercompany account -> (other company, its mirror accounts).
IC_MIRRORS = {}
for (_co_a, _accs_a), (_co_b, _accs_b) in IC_PAIRS:
	for _acc in _accs_a:
		IC_MIRRORS[_acc] = (_co_b, _accs_b)
	for _acc in _accs_b:
		IC_MIRRORS[_acc] = (_co_a, _accs_a)


def _ic_kind(account):
	a = account.lower()
	return "R" if ("receivable" in a or "due from" in a) else "P"

PL = "P&L"
TRANSFER = "Bank / Cash transfer"
INTERCOMPANY = "Intercompany"
BS = "Balance Sheet"
UNCLASSIFIED = "Unclassified - review"
CLASSES = (PL, BS, INTERCOMPANY, TRANSFER, UNCLASSIFIED)

NO_INVOICE = "Customer receipts (no invoice link)"
OPENING_RECEIPTS = "Customer receipts - opening invoices"
WAGES_UNIDENTIFIED = "Wages paid (employee not identified)"
GENERIC_WORDS = {"salaries", "salary", "wages", "wage", "and", "payroll", "the", "for", "pay", "paid"}


def classify(from_date, to_date):
	"""(allocations, cash GL lines) for Bank / Cash lines posted in the window."""
	out, cash = Engine().run()
	f, t = getdate(from_date), getdate(to_date)
	return ([o for o in out if f <= getdate(o.posting_date) <= t],
	        [c for c in cash if f <= getdate(c.posting_date) <= t])


class Engine:
	def __init__(self):
		self.out = []
		self.vlines = {}
		self._inv_cache = {}
		self._vtype = {}
		self._load_accounts()

	# ---- reference data ----------------------------------------------------
	def _load_accounts(self):
		rows = frappe.get_all("Account", filters={"company": ["in", COMPANIES]},
		                      fields=["name", "account_name", "company", "root_type", "account_type",
		                              "parent_account", "is_group"])
		self.acc = {r.name: r for r in rows}
		self.cash_accounts = {r.name for r in rows if r.account_type in CASH_TYPES and not r.is_group}
		for r in rows:
			r.section = self._section(r)
		companies = frappe.get_all("Company", filters={"name": ["in", COMPANIES]},
		                           fields=["name", "abbr", "default_receivable_account", "default_payable_account"])
		self.abbr = {c.name: c.abbr for c in companies}
		self.debtors = {c.default_receivable_account for c in companies}
		self.creditors = {c.default_payable_account for c in companies}
		leaf = [r for r in rows if not r.is_group]
		self.payroll_payable = {r.name for r in leaf if "payroll payable" in (r.account_name or "").lower()}
		self.employee_payable = {r.name for r in leaf if "employee payable" in (r.account_name or "").lower()}
		self.internal_customers = set(frappe.get_all("Customer", filters={"is_internal_customer": 1}, pluck="name"))
		self.internal_suppliers = set(frappe.get_all("Supplier", filters={"is_internal_supplier": 1}, pluck="name"))

	def _section(self, a):
		"""Income / COGS / Opex, from the group directly under the account's root
		(the grouping the accrual P&L shows): "Cost of Goods Sold(s)" and "Direct
		Expenses" are COGS, every other expense group is Opex."""
		if a.root_type == "Income":
			return "Income"
		if a.root_type != "Expense":
			return None
		node, chain = a, []
		while node and node.parent_account:
			chain.append(node)
			node = self.acc.get(node.parent_account)
		top = chain[-1] if chain else a
		name = (top.account_name or "").strip().lower()
		if name.startswith("cost of goods") or name.startswith("direct expense") or name == "cogs":
			return "COGS"
		return "Opex"

	def is_pl(self, account):
		a = self.acc.get(account)
		return bool(a and a.root_type in ("Income", "Expense"))

	def pseudo(self, company, label):
		return f"{label} - {self.abbr.get(company, company)}"

	# ---- output --------------------------------------------------------------
	def emit(self, c, amount, cls, company, head=None, section=None, reason="", review=False,
	         partner=None, via=None, party=None):
		"""amount: the piece of the Bank / Cash line, signed (+ in, - out)."""
		a = self.acc.get(head) if head else None
		section = section or (a.section if a else None)
		pl = 0.0
		if cls == PL:
			pl = amount if section == "Income" else -amount   # income in +, expense out +
		self.out.append(frappe._dict(
			cash_gl=c.name, cash_account=c.account, cash_company=c.company,
			voucher_type=c.voucher_type, voucher_no=c.voucher_no, posting_date=c.posting_date,
			against=c.against, remark=c.remarks, amount=amount, cls=cls, company=company,
			head=head, section=section if cls == PL else None, pl_amount=pl,
			partner=partner, party=party, via=via, via_type=self._vtype.get(via) if via else None,
			reason=reason, review=1 if review else 0,
		))

	# ---- main ----------------------------------------------------------------
	def run(self):
		self.cash_lines = frappe.db.sql("""
			select name, company, account, voucher_type, voucher_no, posting_date, debit, credit,
			       against, party_type, party, remarks, is_opening
			from `tabGL Entry`
			where is_cancelled = 0 and company in %(c)s and account in %(a)s
			  and voucher_type != 'Period Closing Voucher'
			order by posting_date, voucher_no, name""",
			{"c": COMPANIES, "a": tuple(self.cash_accounts) or ("",)}, as_dict=True)
		self._load_lines({(c.voucher_type, c.voucher_no) for c in self.cash_lines})
		self._match_intercompany()
		self._match_payroll()
		self._load_ple_and_refs()
		for c in self.cash_lines:
			self._classify_cash_line(c)
		return self.out, self.cash_lines

	def _load_lines(self, vouchers):
		names = sorted({v[1] for v in vouchers if v not in self.vlines})
		for v in vouchers:
			self.vlines.setdefault(v, [])
		for i in range(0, len(names), 500):
			for g in frappe.db.sql("""
				select name, company, account, voucher_type, voucher_no, posting_date, debit, credit,
				       against, party_type, party, against_voucher_type, against_voucher, remarks, creation
				from `tabGL Entry` where is_cancelled = 0 and voucher_no in %(v)s""",
				{"v": names[i:i + 500]}, as_dict=True):
				key = (g.voucher_type, g.voucher_no)
				self._vtype[g.voucher_no] = g.voucher_type
				if key in self.vlines:
					self.vlines[key].append(g)

	@staticmethod
	def _value(l):
		return abs(flt(l.debit) - flt(l.credit))

	def _partners(self, line, lines):
		"""Lines on the other side of `line` within its voucher that it pays / receives."""
		dr = flt(line.debit) > flt(line.credit)
		opposite = [x for x in lines if x.name != line.name and (flt(x.credit) > EPS if dr else flt(x.debit) > EPS)]
		if len(opposite) <= 1:
			return opposite
		same_side = [x for x in lines if (flt(x.debit) > EPS if dr else flt(x.credit) > EPS)]
		if len(same_side) > 1:
			exact = [x for x in opposite if abs(self._value(x) - self._value(line)) <= EPS]
			if len(exact) == 1:
				return exact
		return opposite

	def _classify_cash_line(self, c):
		amount = flt(c.debit) - flt(c.credit)
		if c.is_opening == "Yes":
			return self.emit(c, amount, BS, c.company, reason="Opening balance entry")
		partners = self._partners(c, self.vlines[(c.voucher_type, c.voucher_no)])
		if not partners:
			return self.emit(c, amount, UNCLASSIFIED, c.company, review=True,
			                 reason="Nothing on the other side of this voucher")
		total = sum(self._value(l) for l in partners)
		for l in partners:
			share = self._value(l) / total if total > EPS else 1.0 / len(partners)
			self._classify(c, amount * share, l, c.company)

	def _classify(self, c, amt, l, company, via=None, depth=0):
		a = self.acc.get(l.account)
		if not a:
			return self.emit(c, amt, UNCLASSIFIED, company, partner=l.account, via=via, review=True,
			                 reason="Account outside the three companies' charts")
		if l.account in self.cash_accounts:
			if company == c.company:
				return self.emit(c, amt, TRANSFER, company, partner=l.account, via=via,
				                 reason="Between two Bank / Cash accounts of the company")
			return self.emit(c, amt, INTERCOMPANY, company, partner=l.account, via=via,
			                 reason=f"Money moved between {c.company} and {company}")
		if a.root_type in ("Income", "Expense"):
			return self.emit(c, amt, PL, company, head=l.account, partner=l.account, via=via)
		if l.account in IC_MIRRORS:
			if depth:
				return self.emit(c, amt, UNCLASSIFIED, company, partner=l.account, via=via, review=True,
				                 reason="The other company's entry passes the amount on to a further intercompany account")
			return self._intercompany(c, amt, l)
		if (l.party_type == "Customer" and l.party) or l.account in self.debtors:
			if l.party in self.internal_customers:
				return self.emit(c, amt, INTERCOMPANY, company, partner=l.account, party=l.party, via=via,
				                 reason=f"Internal customer {l.party}")
			return self._party(c, amt, l, company, "Customer", via)
		if (l.party_type == "Supplier" and l.party) or l.account in self.creditors:
			if l.party in self.internal_suppliers:
				return self.emit(c, amt, INTERCOMPANY, company, partner=l.account, party=l.party, via=via,
				                 reason=f"Internal supplier {l.party}")
			return self._party(c, amt, l, company, "Supplier", via)
		if l.account in self.payroll_payable:
			return self._payroll(c, amt, l, company, via)
		if l.account in self.employee_payable:
			return self.emit(c, amt, BS, company, partner=l.account, via=via,
			                 reason="Employee Payable: funding / reimbursing an expense tracker; "
			                        "the expenses count where the tracker pays them")
		return self.emit(c, amt, BS, company, partner=l.account, via=via,
		                 reason=f"Balance Sheet head ({a.account_type or a.root_type})")

	# ---- customers / suppliers -------------------------------------------------
	def _load_ple_and_refs(self):
		names = sorted({v[1] for v in self.vlines})
		self._ple = collections.defaultdict(list)
		self._ref_text = {}
		for i in range(0, len(names), 500):
			chunk = names[i:i + 500]
			for r in frappe.db.sql("""
				select voucher_type, voucher_no, account, party, against_voucher_type, against_voucher_no,
				       sum(amount) amount
				from `tabPayment Ledger Entry`
				where delinked = 0 and voucher_no in %(v)s
				group by voucher_type, voucher_no, account, party, against_voucher_type, against_voucher_no""",
				{"v": chunk}, as_dict=True):
				# A payment's own Payment Ledger rows are negative; settled = positive.
				self._ple[(r.voucher_type, r.voucher_no, r.account, r.party)].append(
					(r.against_voucher_type, r.against_voucher_no, -flt(r.amount)))
			for r in frappe.db.sql("""select name, concat_ws(' ', title, cheque_no, user_remark) txt
				from `tabJournal Entry` where name in %(v)s""", {"v": chunk}, as_dict=True):
				self._ref_text[r.name] = r.txt or ""
			for r in frappe.db.sql("""select name, concat_ws(' ', party, reference_no, remarks) txt
				from `tabPayment Entry` where name in %(v)s""", {"v": chunk}, as_dict=True):
				self._ref_text[r.name] = r.txt or ""

	def _settled(self, l):
		"""How much of the party line settles the receivable / payable (+)."""
		a = self.acc.get(l.account)
		if a and a.account_type == "Receivable":
			return flt(l.credit) - flt(l.debit)
		return flt(l.debit) - flt(l.credit)

	def _allocations(self, l):
		"""[(against doctype, against name, weight)] for a party line; doctype None
		is the part not allocated to any document."""
		if l.against_voucher and l.against_voucher_type and l.against_voucher != l.voucher_no:
			return [(l.against_voucher_type, l.against_voucher, 1.0)]
		lines = [x for x in self.vlines.get((l.voucher_type, l.voucher_no), [])
		         if x.account == l.account and x.party == l.party]
		linked = collections.defaultdict(float)
		unlinked = 0.0
		for x in lines:
			if x.against_voucher and x.against_voucher != x.voucher_no:
				linked[x.against_voucher] += self._settled(x)
			else:
				unlinked += self._settled(x)
		remaining = []
		for avt, avn, amt in self._ple.get((l.voucher_type, l.voucher_no, l.account, l.party), []):
			if avn == l.voucher_no:
				continue
			left = amt - linked.pop(avn, 0.0)
			if abs(left) > EPS:
				remaining.append((avt, avn, left))
		if abs(unlinked) <= EPS:
			return [(None, None, 1.0)]
		total = sum(x[2] for x in remaining)
		if not remaining or total * unlinked <= 0 or any(x[2] * unlinked < 0 for x in remaining):
			return [(None, None, 1.0)]
		scale = min(1.0, unlinked / total)
		out = [(avt, avn, left * scale / unlinked) for avt, avn, left in remaining]
		rest = 1.0 - sum(x[2] for x in out)
		if rest > 1e-9:
			out.append((None, None, rest))
		return out

	def _party(self, c, amt, l, company, kind, via):
		invoice = "Sales Invoice" if kind == "Customer" else "Purchase Invoice"
		for avt, avn, w in self._allocations(l):
			part = amt * w
			if abs(part) < 1e-9:
				continue
			if avt in (invoice, "Journal Entry"):
				self._document(c, part, l, company, kind, avt, avn, via)
			else:
				self._unallocated(c, part, l, company, kind, via, avn)

	def _unallocated(self, c, amt, l, company, kind, via, other=None):
		extra = f" (settled against {other})" if other else ""
		if kind == "Customer":
			return self.emit(c, amt, PL, company, head=self.pseudo(company, NO_INVOICE), section="Income",
			                 partner=l.account, party=l.party, via=via, review=True,
			                 reason="Customer payment not allocated to any invoice" + extra +
			                        ": counted as income, income head not determinable")
		return self.emit(c, amt, UNCLASSIFIED, company, partner=l.account, party=l.party, via=via, review=True,
		                 reason="Supplier payment not allocated to any invoice" + extra +
		                        ": could be an expense, inventory, an asset or a deposit")

	def _document_heads(self, doctype, name, kind):
		"""[(account, value)] on the other side of the party in an invoice / journal."""
		key = (doctype, name, kind)
		if key in self._inv_cache:
			return self._inv_cache[key]
		lines = frappe.db.sql("""select account, debit, credit, party from `tabGL Entry`
			where is_cancelled = 0 and voucher_type = %s and voucher_no = %s""", (doctype, name), as_dict=True)
		party_types = ("Receivable", "Payable")
		other = [l for l in lines
		         if not (l.party and (self.acc.get(l.account) or frappe._dict()).account_type in party_types)]
		if kind == "Customer":
			sign = lambda l: flt(l.credit) - flt(l.debit)   # noqa: E731
		else:
			sign = lambda l: flt(l.debit) - flt(l.credit)   # noqa: E731
		vals = collections.defaultdict(float)
		if doctype == "Sales Invoice":
			# Only what the customer was charged: the items' income accounts and the
			# tax heads. Leaves out the stock / cost of goods lines an invoice with
			# Update Stock also posts.
			keep = set(frappe.get_all("Sales Invoice Item", filters={"parent": name}, pluck="income_account"))
			keep |= set(frappe.get_all("Sales Taxes and Charges",
			                           filters={"parent": name, "parenttype": "Sales Invoice"}, pluck="account_head"))
			for l in other:
				if l.account in keep:
					vals[l.account] += sign(l)
		if not vals:
			for l in other:
				vals[l.account] += sign(l)
		if doctype == "Journal Entry":
			vals = {k: v for k, v in vals.items() if v > EPS}
		heads = [(k, v) for k, v in vals.items() if abs(v) > EPS]
		self._inv_cache[key] = heads
		return heads

	def _document(self, c, amt, l, company, kind, doctype, name, via):
		self._vtype[name] = doctype
		heads = self._document_heads(doctype, name, kind)
		gross = sum(v for _k, v in heads)
		if not heads or abs(gross) <= EPS:
			return self._unallocated(c, amt, l, company, kind, via, name)
		for account, v in heads:
			part = amt * v / gross
			a = self.acc.get(account)
			opening = a and (a.account_type == "Temporary" or a.root_type == "Equity")
			if a and a.root_type in ("Income", "Expense"):
				self.emit(c, part, PL, company, head=account, partner=l.account, party=l.party, via=name)
			elif opening and kind == "Customer":
				self.emit(c, part, PL, company, head=self.pseudo(company, OPENING_RECEIPTS), section="Income",
				          partner=account, party=l.party, via=name, review=True,
				          reason=f"Customer paid an opening (pre-system) balance {name}: counted as income, "
				                 "income head not recorded")
			elif opening:
				self.emit(c, part, UNCLASSIFIED, company, partner=account, party=l.party, via=name, review=True,
				          reason=f"Paid an opening (pre-system) bill {name}: what it was for is not recorded")
			elif kind == "Customer":
				self.emit(c, part, BS, company, partner=account, party=l.party, via=name,
				          reason=f"Customer receipt, share of {name} that is not income "
				                 f"({(a.account_type or a.root_type) if a else 'tax / other'})")
			else:
				what = (a.account_type or a.root_type) if a else "other"
				self.emit(c, part, BS, company, partner=account, party=l.party, via=name,
				          reason=f"Supplier payment for a Balance Sheet item on {name} ({what})")

	# ---- payroll ---------------------------------------------------------------
	def _match_payroll(self):
		self._payroll_match = {}
		self._payroll_heads = collections.defaultdict(dict)    # company -> head -> name words
		self._payroll_section = {}
		if not self.payroll_payable:
			return
		pp = tuple(self.payroll_payable)
		accruals = frappe.db.sql("""
			select g.name, g.company, g.account, g.posting_date, g.credit, g.voucher_type, g.voucher_no,
			       (select d.account from `tabGL Entry` d where d.voucher_no = g.voucher_no and d.is_cancelled = 0
			          and d.debit > 0 and d.account not in %(p)s order by d.debit desc limit 1) head
			from `tabGL Entry` g
			where g.is_cancelled = 0 and g.credit > 0 and g.account in %(p)s
			  and not exists (select 1 from `tabGL Entry` x where x.voucher_no = g.voucher_no
			                  and x.is_cancelled = 0 and x.account in %(cash)s)""",
			{"p": pp, "cash": tuple(self.cash_accounts)}, as_dict=True)
		payments = frappe.db.sql("""select name, company, account, posting_date, debit, voucher_no
			from `tabGL Entry` where is_cancelled = 0 and debit > 0 and account in %(p)s""", {"p": pp}, as_dict=True)
		by_amount = collections.defaultdict(list)
		sections = collections.defaultdict(set)
		for r in accruals:
			self._vtype[r.voucher_no] = r.voucher_type
			by_amount[(r.account, round(flt(r.credit), 2))].append(r)
			h = self.acc.get(r.head)
			if h and h.root_type == "Expense":
				sections[r.company].add(h.section)
				words = set(re.findall(r"[a-z]{3,}", (h.account_name or "").lower())) - GENERIC_WORDS
				if words:
					self._payroll_heads[r.company][r.head] = words
		self._payroll_section = {co: next(iter(s)) for co, s in sections.items() if len(s) == 1}
		self._accruals = accruals
		pairs = []
		for p in payments:
			for r in by_amount.get((p.account, round(flt(p.debit), 2)), []):
				gap = abs((getdate(p.posting_date) - getdate(r.posting_date)).days)
				if gap <= PAYROLL_DAYS:
					pairs.append((gap, p.name, r.name, r))
		pairs.sort(key=lambda x: x[:3])
		used = set()
		for _gap, pn, rn, r in pairs:
			if pn in self._payroll_match or rn in used:
				continue
			used.add(rn)
			self._payroll_match[pn] = r

	def _payroll(self, c, amt, l, company, via):
		r = self._payroll_match.get(l.name)
		if not r:
			# The payment line's own amount may be mistyped (an intercompany twin):
			# the payroll posting of the cash actually paid, up to 20 days earlier.
			value, paid_on = round(abs(amt), 2), getdate(c.posting_date)
			cands = [a for a in getattr(self, "_accruals", []) if a.company == company and a.account == l.account
			         and round(flt(a.credit), 2) == value and 0 <= (paid_on - getdate(a.posting_date)).days <= 20]
			if cands:
				r = min(cands, key=lambda a: (paid_on - getdate(a.posting_date)).days)
		if r and self.is_pl(r.head):
			return self.emit(c, amt, PL, company, head=r.head, partner=l.account, via=via or r.voucher_no,
			                 reason=f"Payroll posting {r.voucher_no} of the same amount")
		if r and r.head:
			return self.emit(c, amt, BS, company, partner=r.head, via=via or r.voucher_no,
			                 reason=f"Payroll posting {r.voucher_no} charged a Balance Sheet head")
		text = set(re.findall(r"[a-z]{3,}", self._ref_text.get(l.voucher_no, "").lower())) - GENERIC_WORDS
		named = [h for h, words in self._payroll_heads.get(company, {}).items() if words & text]
		if len(named) == 1:
			return self.emit(c, amt, PL, company, head=named[0], partner=l.account, via=via,
			                 reason="Employee named in the payment reference")
		section = self._payroll_section.get(company)
		if section:
			return self.emit(c, amt, PL, company, head=self.pseudo(company, WAGES_UNIDENTIFIED), section=section,
			                 partner=l.account, via=via, review=True,
			                 reason="Payroll paid; no posting of this amount and no employee name in the reference. "
			                        f"Every payroll posting of {company} is {section}")
		return self.emit(c, amt, UNCLASSIFIED, company, partner=l.account, via=via, review=True,
		                 reason="Payroll paid; wages head not determinable")

	# ---- intercompany ------------------------------------------------------------
	def _match_intercompany(self):
		"""Pair intercompany lines in Bank / Cash vouchers with their mirror line in
		the other company: opposite side, same amount, nearest date. All dates at
		once, nearest pairs first, each line used once."""
		self._ic_match = {}
		accounts = set(IC_MIRRORS) | {m for _co, ms in IC_MIRRORS.values() for m in ms}
		pool = collections.defaultdict(list)
		for r in frappe.db.sql("""select name, company, account, posting_date, debit, credit, voucher_type,
			voucher_no, creation, remarks from `tabGL Entry` where is_cancelled = 0 and account in %(a)s""",
			{"a": tuple(accounts)}, as_dict=True):
			pool[r.account].append(r)
		self._ic_pool = pool
		demand = [l for lines in self.vlines.values() for l in lines if l.account in IC_MIRRORS]
		pairs = []
		for d in demand:
			_co, mirrors = IC_MIRRORS[d.account]
			value, d_dr = self._value(d), flt(d.debit) > flt(d.credit)
			for m in mirrors:
				for r in pool.get(m, []):
					rv = flt(r.credit) if d_dr else flt(r.debit)
					diff = abs(rv - value)
					if rv <= EPS:
						continue
					gap = abs((getdate(r.posting_date) - getdate(d.posting_date)).days)
					together = abs((r.creation - d.creation).total_seconds()) <= IC_TOGETHER_SECONDS
					both_cash = (r.voucher_type, r.voucher_no) in self.vlines
					if diff <= EPS and gap <= IC_DAYS:
						tier = 0
					elif diff <= EPS and together:
						tier = 1      # keyed in as a pair; one of the dates is mistyped
					elif diff <= IC_CENTS and gap <= IC_WIDE_DAYS:
						tier = 2
					elif both_cash and gap <= IC_SHORT_DAYS and diff <= max(1.0, value * IC_SHORT_RATIO):
						# Money out of one company's bank, into the other's, same few
						# days, amounts a little apart: the same movement, booked short
						# on one side. Matched for the smaller amount; the excess stays
						# Unclassified.
						tier = 3
					else:
						continue
					label = 0 if _ic_kind(d.account) != _ic_kind(r.account) else 1
					pairs.append((tier, round(diff, 2), gap, label, d.name, r.name, d, r))
		# Nearest first: exact before cents, same day before later, the usual
		# Receivable <-> Payable labelling before a same-label pair.
		pairs.sort(key=lambda x: x[:6])
		used = set()
		for tier, diff, gap, _label, dn, rn, d, r in pairs:
			if dn in used or rn in used:
				continue
			used.update((dn, rn))
			self._ic_match[dn] = (r, tier, diff, gap)
			self._ic_match.setdefault(rn, (d, tier, diff, gap))
		# Twins keyed with different amounts: on one posting date, exactly one
		# line left unmatched on each side of a company pair, in opposite
		# directions, amounts within IC_TWIN_RATIO. One movement, mistyped on one
		# side; the cash side's amount is what moved.
		groups = collections.defaultdict(lambda: ([], []))
		for d in demand:
			if d.name not in used:
				co, _m = IC_MIRRORS[d.account]
				groups[(d.company, co, getdate(d.posting_date), flt(d.debit) > flt(d.credit))][0].append(d)
		for acc, rows in pool.items():
			co, _m = IC_MIRRORS[acc]
			for r in rows:
				if r.name not in used:
					groups[(co, r.company, getdate(r.posting_date), flt(r.credit) > flt(r.debit))][1].append(r)
		for ds, rs in groups.values():
			if len(ds) == 1 and len(rs) == 1:
				d, r = ds[0], rs[0]
				value, rv = self._value(d), self._value(r)
				if abs(rv - value) <= max(value, rv) * IC_TWIN_RATIO:
					used.update((d.name, r.name))
					self._ic_match[d.name] = (r, 4, abs(rv - value), 0)
					self._ic_match.setdefault(r.name, (d, 4, abs(rv - value), 0))
		self._ic_used = used
		self._load_lines({(m[0].voucher_type, m[0].voucher_no) for m in self._ic_match.values()})

	def _intercompany(self, c, amt, l):
		other_co, _mirrors = IC_MIRRORS[l.account]
		m = self._ic_match.get(l.name)
		if not m and self._ic_unbooked_wages(c, amt, l, other_co):
			return
		if not m:
			return self.emit(c, amt, UNCLASSIFIED, c.company, partner=l.account, review=True,
			                 reason=f"Intercompany with {other_co}: no entry of {self._value(l):,.2f} on the other "
			                        f"side in {other_co} within {IC_WIDE_DAYS} days" + self._near_ic(l))
		r, tier, diff, gap = m
		if tier == 3:
			own, other = self._value(l), self._value(r)
			ratio = min(own, other) / own if own > EPS else 1.0
			self.emit(c, amt * ratio, INTERCOMPANY, c.company, partner=l.account, via=r.voucher_no,
			          reason=f"Money moved between {c.company} and {other_co}: {other_co} booked "
			                 f"{other:,.2f} in {r.voucher_no}, {c.company} {own:,.2f}; matched for the smaller amount")
			if ratio < 1:
				self.emit(c, amt * (1 - ratio), UNCLASSIFIED, c.company, partner=l.account, via=r.voucher_no,
				          review=True,
				          reason=f"{c.company} booked {own - other:,.2f} more than {other_co} did for the same "
				                 f"movement ({r.voucher_no}: {other:,.2f}); no transaction accounts for the difference")
			return
		note = ""
		if tier == 4:
			note = (f" with {self._value(r):,.2f} where {c.company} paid {self._value(l):,.2f}: the amounts disagree, "
			        "one side is mistyped")
		elif tier:
			note = f" (matched {gap} days apart" + (f", amounts differ by {diff:,.2f}" if diff > EPS else "") + ")"
		mv = self.vlines.get((r.voucher_type, r.voucher_no), [])
		mirror = next((x for x in mv if x.name == r.name), None)
		partners = self._partners(mirror, mv) if mirror else []
		total = sum(self._value(x) for x in partners)
		if not partners or total <= EPS:
			return self.emit(c, amt, UNCLASSIFIED, c.company, partner=l.account, via=r.voucher_no, review=True,
			                 reason=f"Mirror {r.voucher_no} in {other_co} has nothing on its other side" + note)
		for x in partners:
			part = amt * self._value(x) / total
			if x.account in self.cash_accounts:
				self.emit(c, part, INTERCOMPANY, c.company, partner=l.account, via=r.voucher_no,
				          reason=f"Money moved between {c.company} and {other_co} "
				                 f"({x.account} in {r.voucher_no}){note}")
			else:
				before = len(self.out)
				self._classify(c, part, x, other_co, via=r.voucher_no, depth=1)
				for o in self.out[before:]:
					o.reason = (f"Paid / received by {c.company} for {other_co} via {l.account}; "
					            f"{other_co} booked it in {r.voucher_no}{note}") + (f". {o.reason}" if o.reason else "")
					if tier == 4:
						o.review = 1

	def _ic_unbooked_wages(self, c, amt, l, other_co):
		"""Wages paid for the other company that it never booked: its own payroll
		posting of exactly this amount, up to 20 days before the payment, names
		the wages head. Flagged so the missing entry gets booked."""
		if not flt(l.debit) > flt(l.credit):
			return False
		value, paid_on = round(self._value(l), 2), getdate(c.posting_date)
		cands = [r for r in getattr(self, "_accruals", [])
		         if r.company == other_co and round(flt(r.credit), 2) == value and self.is_pl(r.head)
		         and 0 <= (paid_on - getdate(r.posting_date)).days <= 20]
		if not cands:
			return False
		r = min(cands, key=lambda x: (paid_on - getdate(x.posting_date)).days)
		self.emit(c, amt, PL, other_co, head=r.head, partner=l.account, via=r.voucher_no, review=True,
		          reason=f"Paid by {c.company} for {other_co} via {l.account}; {other_co} has not booked this payment. "
		                 f"Its payroll posting {r.voucher_no} ({r.posting_date}, same amount) names the wages head")
		return True

	def _near_ic(self, l):
		_co, mirrors = IC_MIRRORS[l.account]
		value, d_dr = self._value(l), flt(l.debit) > flt(l.credit)
		best = None
		for m in mirrors:
			for r in self._ic_pool.get(m, []):
				rv = flt(r.credit) if d_dr else flt(r.debit)
				gap = abs((getdate(r.posting_date) - getdate(l.posting_date)).days)
				if rv > EPS and abs(rv - value) <= max(1.0, value * 0.01) and gap <= 31:
					k = (abs(rv - value), gap)
					if best is None or k < best[0]:
						best = (k, r, rv, gap)
		if not best:
			return ""
		_k, r, rv, gap = best
		taken = " (already matched to another line)" if r.name in self._ic_used else ""
		return f"; closest: {r.voucher_no} {rv:,.2f} on {r.posting_date}, {gap} days{taken}"
