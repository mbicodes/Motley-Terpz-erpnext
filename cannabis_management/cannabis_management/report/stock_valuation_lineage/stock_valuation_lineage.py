# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""
Stock Valuation Lineage
=======================

For every unit of stock that leaves the system through a **Sales Invoice** or a
**Delivery Note**, this report reconstructs the *complete backward journey* of
that stock -- from the moment it was sold, back through every phase it moved
through (repack / production, transfer, consumption, purchase / opening), and
shows the **valuation rate at each phase** together with the exact ERP document
that established that rate.

How the back-trace works
------------------------
This site does NOT populate batch / serial tracking on Stock Ledger Entries
(0 of ~11k SLEs carry a batch), so lineage cannot be followed batch-by-batch.
Instead the lineage is followed by **item + warehouse** through the Stock
Ledger and through **Repack** consumption links (Repack is the dominant
production mechanism on this site):

  Sold (SI / DN)                         <- valuation rate at sale (COGS rate)
    -> Produced (Repack / Manufacture)   <- rate the finished good was costed at
         -> Consumed Input (item A)      <- rate item A was consumed at
              -> Produced / Purchased ... <- where item A itself came from
         -> Consumed Input (item B)
              -> ...
    -> Purchased (Purchase Receipt)      <- terminal: entered our system
    -> Opening / Reconciliation          <- terminal: opening value
    -> Transferred In (Material Transfer)-> follows to the source warehouse

The recursion stops (a branch is a leaf) the moment no earlier producing /
receiving event can be found for an item in a warehouse -- i.e. "the moment you
don't find any back working, stop". Different items therefore naturally produce
different numbers of phases / depth.

Performance
-----------
The whole ledger needed for the trace is **pre-loaded in a handful of bulk
queries** and the recursion then runs entirely in memory. This avoids the
per-node "N+1" query explosion so the report loads quickly even over large
date ranges. Output is capped (Row Limit filter) at the sold-line boundary so
each included sale keeps a complete lineage.

Caveat surfaced to the user: because valuation is moving-average and there are
no batches, the "producing" event chosen for a given item+warehouse is the most
recent inbound/producing event at or before the consuming/selling moment. This
is the best-effort, honest reconstruction available from the ledger.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Stock Entry purposes that consume inputs to produce an output -> we recurse
# into what they consumed.
PRODUCTION_PURPOSES = ("Repack", "Manufacture")
# Stock Entry purposes that just move the SAME item between warehouses -> we
# follow to the source warehouse.
TRANSFER_PURPOSES = ("Material Transfer", "Material Transfer for Manufacture")
# Stock Entry purposes that bring NEW stock in from outside -> terminal.
RECEIPT_PURPOSES = ("Material Receipt",)

DEFAULT_ROW_LIMIT = 5000  # rows emitted before truncating (at sold-line boundary)
HARD_ROW_LIMIT = 50000    # absolute ceiling regardless of filter


def execute(filters=None):
    filters = frappe._dict(filters or {})
    engine = LineageEngine(filters)
    data = engine.build()
    return get_columns(), data, None, None, engine.report_summary()


@frappe.whitelist()
def get_item_lineage(item_code, warehouse, voucher_type, voucher_no):
    """On-demand backward valuation trace for ONE sold line - same engine as
    the full report above, just seeded from a single known (item, warehouse,
    voucher) instead of a filtered sweep of sold lines across a date range.
    Used by the Profit and Loss (Drilldown) page: a COGS item row expands
    straight into its lineage on click, without pre-computing this for every
    item up front (which would be prohibitively expensive over a whole
    report run)."""
    sle = frappe.db.sql(
        """
        SELECT name, item_code, warehouse, actual_qty, incoming_rate,
               valuation_rate, voucher_type, voucher_no, posting_date, posting_datetime
        FROM `tabStock Ledger Entry`
        WHERE is_cancelled = 0 AND actual_qty < 0
          AND item_code = %(item_code)s AND warehouse = %(warehouse)s
          AND voucher_type = %(voucher_type)s AND voucher_no = %(voucher_no)s
        ORDER BY posting_datetime DESC
        LIMIT 1
        """,
        {
            "item_code": item_code,
            "warehouse": warehouse,
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
        },
        as_dict=True,
    )
    if not sle:
        return []

    engine = LineageEngine(frappe._dict({}))
    engine._preload()

    sold = sle[0]
    name, uom = engine._item(sold.item_code)
    rate = flt(sold.valuation_rate) or flt(sold.incoming_rate)
    engine._emit(
        phase=_("Sold"),
        item_code=sold.item_code,
        item_name=name,
        qty=flt(sold.actual_qty),
        uom=uom,
        rate=rate,
        warehouse=sold.warehouse,
        voucher_type=sold.voucher_type,
        voucher_no=sold.voucher_no,
        posting_date=sold.posting_date,
        sle=sold.name,
        indent=0,
    )
    engine._trace_origin(
        item_code=sold.item_code,
        warehouse=sold.warehouse,
        before_dt=sold.posting_datetime,
        indent=1,
        visited=set(),
        expanded_se=frozenset(),
        depth=1,
    )
    return engine.rows


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------
def get_columns():
    return [
        {"label": _("Phase"), "fieldname": "phase", "fieldtype": "Data", "width": 260},
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link",
         "options": "Item", "width": 150},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 100,
         "precision": 3},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
        {"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency",
         "width": 130},
        {"label": _("Value at Phase"), "fieldname": "amount", "fieldtype": "Currency",
         "width": 140},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 180},
        {"label": _("Document Type"), "fieldname": "voucher_type", "fieldtype": "Data",
         "width": 130},
        {"label": _("Document"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 200},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date",
         "width": 100},
        {"label": _("Stock Ledger Entry"), "fieldname": "stock_ledger_entry", "fieldtype": "Link",
         "options": "Stock Ledger Entry", "width": 190},
    ]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class LineageEngine:
    def __init__(self, filters):
        self.filters = filters
        self.max_depth = int(filters.get("max_depth") or 15)
        row_limit = int(filters.get("row_limit") or DEFAULT_ROW_LIMIT)
        self.row_limit = max(1, min(row_limit, HARD_ROW_LIMIT))
        self.rows = []
        self._truncated = False
        # in-memory indexes (populated by _preload)
        self._inbound = {}        # (item, warehouse) -> [rows] desc by posting_datetime
        self._se_out_sle = {}     # (voucher_no, item, warehouse) -> row
        self._se_sources = {}     # se name -> [consumed source rows]
        self._se_transfer = {}    # (se name, item) -> source warehouse
        self._se_purpose = {}     # se name -> purpose
        self._item_meta = {}      # item_code -> (item_name, stock_uom)

    # -- public -----------------------------------------------------------
    def build(self):
        sold_lines = self._get_sold_lines()
        if not sold_lines:
            return []
        self._preload()
        for sold in sold_lines:
            # Cap at the sold-line boundary so each lineage stays complete.
            if len(self.rows) >= self.row_limit:
                self._truncated = True
                break
            name, uom = self._item(sold.item_code)
            rate = flt(sold.valuation_rate) or flt(sold.incoming_rate)
            self._emit(
                phase=_("Sold"),
                item_code=sold.item_code,
                item_name=name,
                qty=flt(sold.actual_qty),
                uom=uom,
                rate=rate,
                warehouse=sold.warehouse,
                voucher_type=sold.voucher_type,
                voucher_no=sold.voucher_no,
                posting_date=sold.posting_date,
                sle=sold.name,
                indent=0,
            )
            self._trace_origin(
                item_code=sold.item_code,
                warehouse=sold.warehouse,
                before_dt=sold.posting_datetime,
                indent=1,
                visited=set(),
                expanded_se=frozenset(),
                depth=1,
            )
        return self.rows

    def report_summary(self):
        summary = [
            {"label": _("Sold Lines Traced"),
             "value": sum(1 for r in self.rows if r["indent"] == 0),
             "indicator": "Blue"},
            {"label": _("Total Lineage Rows"), "value": len(self.rows), "indicator": "Green"},
        ]
        if self._truncated:
            summary.append({
                "label": _("Truncated"),
                "value": _("Row limit {0} reached -- narrow the filters or raise Row Limit")
                .format(self.row_limit),
                "indicator": "Orange",
            })
        return summary

    # -- recursion (pure in-memory) --------------------------------------
    def _trace_origin(self, item_code, warehouse, before_dt, indent, visited,
                      expanded_se, depth, exclude_voucher=None):
        if depth > self.max_depth or len(self.rows) >= self.row_limit:
            return

        origin = self._get_origin_sle(item_code, warehouse, before_dt, exclude_voucher)
        if not origin:
            # No earlier backworking for this item in this warehouse -> stop.
            return

        vkey = (item_code, warehouse, origin["voucher_no"])
        if vkey in visited:
            return  # cycle guard (same item re-entering the same voucher)
        visited = visited | {vkey}

        vtype = origin["voucher_type"]
        purpose = self._se_purpose.get(origin["voucher_no"]) if vtype == "Stock Entry" else None
        phase, is_production, is_transfer = _classify(vtype, purpose)
        rate = flt(origin["incoming_rate"]) or flt(origin["valuation_rate"])
        name, uom = self._item(item_code)
        se = origin["voucher_no"]

        # A production Stock Entry already expanded upstream in THIS branch must
        # not have its whole input tree walked again (multi-output repacks would
        # otherwise re-expand combinatorially).
        already_expanded = is_production and se in expanded_se

        self._emit(
            phase=(_("{0} [already detailed above]").format(phase)
                   if already_expanded else phase),
            item_code=item_code,
            item_name=name,
            qty=flt(origin["actual_qty"]),
            uom=uom,
            rate=rate,
            warehouse=warehouse,
            voucher_type=vtype,
            voucher_no=se,
            posting_date=origin["posting_date"],
            sle=origin["name"],
            indent=indent,
        )

        if is_production and not already_expanded:
            se_dt = origin["posting_datetime"]
            child_expanded = expanded_se | {se}
            for src in self._se_sources.get(se, []):
                if len(self.rows) >= self.row_limit:
                    return
                cons = self._se_out_sle.get((se, src["item_code"], src["s_warehouse"]))
                crate = flt(cons["valuation_rate"]) if cons else flt(src["valuation_rate"])
                cqty = -abs(flt(cons["actual_qty"])) if cons else -abs(flt(src["qty"]))
                cname, cuom = self._item(src["item_code"])
                self._emit(
                    phase=_("Consumed Input"),
                    item_code=src["item_code"],
                    item_name=cname,
                    qty=cqty,
                    uom=cuom,
                    rate=crate,
                    warehouse=src["s_warehouse"],
                    voucher_type="Stock Entry",
                    voucher_no=se,
                    posting_date=origin["posting_date"],
                    sle=cons["name"] if cons else None,
                    indent=indent + 1,
                )
                # Trace where this input came from BEFORE it was consumed here:
                # exclude this SE so an item both produced & consumed in the same
                # entry cannot trace back to itself.
                self._trace_origin(
                    item_code=src["item_code"],
                    warehouse=src["s_warehouse"],
                    before_dt=se_dt,
                    indent=indent + 2,
                    visited=visited,
                    expanded_se=child_expanded,
                    depth=depth + 1,
                    exclude_voucher=se,
                )
        elif is_transfer:
            src_wh = self._se_transfer.get((se, item_code))
            if src_wh and src_wh != warehouse:
                self._trace_origin(
                    item_code=item_code,
                    warehouse=src_wh,
                    before_dt=origin["posting_datetime"],
                    indent=indent + 1,
                    visited=visited,
                    expanded_se=expanded_se,
                    depth=depth + 1,
                    exclude_voucher=se,
                )
        # else terminal (Purchase Receipt / Material Receipt / Reconciliation)

    def _get_origin_sle(self, item_code, warehouse, before_dt, exclude_voucher=None):
        for r in self._inbound.get((item_code, warehouse), ()):
            if exclude_voucher and r["voucher_no"] == exclude_voucher:
                continue
            if r["posting_datetime"] <= before_dt:
                return r
        return None

    # -- row helper -------------------------------------------------------
    def _emit(self, phase, item_code, item_name, qty, uom, rate, warehouse,
              voucher_type, voucher_no, posting_date, sle, indent):
        self.rows.append({
            "phase": phase,
            "item_code": item_code,
            "item_name": item_name,
            "qty": qty,
            "uom": uom,
            "valuation_rate": rate,
            "amount": abs(qty) * rate,
            "warehouse": warehouse,
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
            "posting_date": posting_date,
            "stock_ledger_entry": sle,
            "indent": indent,
        })

    # -- bulk preload -----------------------------------------------------
    def _preload(self):
        # 1) All inbound / reconciliation SLEs, indexed by (item, warehouse),
        #    newest first -> origin lookups become an in-memory scan.
        inbound = frappe.db.sql(
            """
            SELECT name, item_code, warehouse, voucher_type, voucher_no,
                   incoming_rate, valuation_rate, actual_qty, posting_date,
                   posting_datetime
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
              AND (actual_qty > 0 OR voucher_type = 'Stock Reconciliation')
            ORDER BY posting_datetime DESC, creation DESC
            """, as_dict=True)
        for r in inbound:
            self._inbound.setdefault((r.item_code, r.warehouse), []).append(r)

        # 2) All outgoing Stock Entry SLEs (consumption rates), keyed exactly.
        se_out = frappe.db.sql(
            """
            SELECT name, item_code, warehouse, voucher_no, valuation_rate, actual_qty
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0 AND actual_qty < 0 AND voucher_type = 'Stock Entry'
            """, as_dict=True)
        for r in se_out:
            self._se_out_sle[(r.voucher_no, r.item_code, r.warehouse)] = r

        # 3) Stock Entry purposes.
        for r in frappe.db.sql(
                "SELECT name, purpose FROM `tabStock Entry` WHERE docstatus = 1",
                as_dict=True):
            self._se_purpose[r.name] = r.purpose

        # 4) Stock Entry Detail for production/transfer SEs -> consumed sources
        #    and transfer source-warehouse lookup.
        details = frappe.db.sql(
            """
            SELECT sed.parent, sed.item_code, sed.s_warehouse, sed.t_warehouse,
                   sed.qty, sed.valuation_rate
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.docstatus = 1
              AND se.purpose IN ('Repack','Manufacture','Material Transfer',
                                 'Material Transfer for Manufacture')
              AND sed.s_warehouse IS NOT NULL AND sed.s_warehouse != ''
            """, as_dict=True)
        # A single SE can list the same (item, source warehouse) on several
        # lines -> collapse them into one consumed row (sum the qty) so the tree
        # shows each input once.
        src_agg = {}  # (parent, item, s_wh) -> row
        for r in details:
            self._se_transfer.setdefault((r.parent, r.item_code), r.s_warehouse)
            if r.t_warehouse:
                continue  # produced line, not a consumed source
            key = (r.parent, r.item_code, r.s_warehouse)
            if key in src_agg:
                src_agg[key]["qty"] = flt(src_agg[key]["qty"]) + flt(r.qty)
            else:
                src_agg[key] = r
        for (parent, _item, _wh), row in src_agg.items():
            self._se_sources.setdefault(parent, []).append(row)

        # 5) Item meta (name + uom) for every item we might display.
        for r in frappe.db.sql(
                "SELECT name, item_name, stock_uom FROM `tabItem`", as_dict=True):
            self._item_meta[r.name] = (r.item_name, r.stock_uom)

    def _item(self, item_code):
        return self._item_meta.get(item_code, (item_code, None))

    # -- sold lines (the only filtered query) -----------------------------
    def _get_sold_lines(self):
        f = self.filters
        conditions = ["sle.is_cancelled = 0", "sle.actual_qty < 0"]
        params = {}

        doc_type = f.get("sales_document_type") or "Both"
        if doc_type == "Sales Invoice":
            vtypes = ("Sales Invoice",)
        elif doc_type == "Delivery Note":
            vtypes = ("Delivery Note",)
        else:
            vtypes = ("Sales Invoice", "Delivery Note")
        conditions.append("sle.voucher_type IN %(vtypes)s")
        params["vtypes"] = vtypes

        if f.get("from_date"):
            conditions.append("sle.posting_date >= %(from_date)s")
            params["from_date"] = f.from_date
        if f.get("to_date"):
            conditions.append("sle.posting_date <= %(to_date)s")
            params["to_date"] = f.to_date
        if f.get("item_code"):
            conditions.append("sle.item_code = %(item_code)s")
            params["item_code"] = f.item_code
        if f.get("warehouse"):
            conditions.append("sle.warehouse = %(warehouse)s")
            params["warehouse"] = f.warehouse
        if f.get("voucher_no"):
            conditions.append("sle.voucher_no = %(voucher_no)s")
            params["voucher_no"] = f.voucher_no
        if f.get("company"):
            conditions.append("sle.company = %(company)s")
            params["company"] = f.company
        if f.get("customer"):
            vouchers = self._vouchers_for_customer(f.customer, vtypes)
            if not vouchers:
                return []
            conditions.append("sle.voucher_no IN %(cust_vouchers)s")
            params["cust_vouchers"] = tuple(vouchers)

        return frappe.db.sql(
            """
            SELECT sle.name, sle.item_code, sle.warehouse, sle.actual_qty,
                   sle.incoming_rate, sle.valuation_rate, sle.voucher_type,
                   sle.voucher_no, sle.posting_date, sle.posting_datetime
            FROM `tabStock Ledger Entry` sle
            WHERE {conditions}
            ORDER BY sle.posting_datetime DESC, sle.voucher_no, sle.item_code
            """.format(conditions=" AND ".join(conditions)),
            params, as_dict=True,
        )

    def _vouchers_for_customer(self, customer, vtypes):
        vouchers = []
        if "Sales Invoice" in vtypes:
            vouchers += [d.name for d in frappe.get_all(
                "Sales Invoice", filters={"customer": customer, "docstatus": 1},
                fields=["name"])]
        if "Delivery Note" in vtypes:
            vouchers += [d.name for d in frappe.get_all(
                "Delivery Note", filters={"customer": customer, "docstatus": 1},
                fields=["name"])]
        return vouchers


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _classify(voucher_type, purpose):
    """Return (phase_label, is_production, is_transfer)."""
    if voucher_type == "Purchase Receipt":
        return _("Purchased (Origin)"), False, False
    if voucher_type == "Stock Reconciliation":
        return _("Opening / Reconciliation (Origin)"), False, False
    if voucher_type == "Stock Entry":
        if purpose in PRODUCTION_PURPOSES:
            return _("Produced ({0})").format(purpose), True, False
        if purpose in TRANSFER_PURPOSES:
            return _("Transferred In"), False, True
        if purpose in RECEIPT_PURPOSES:
            return _("Material Receipt (Origin)"), False, False
        return _("Stock Entry ({0})").format(purpose or "?"), False, False
    # Fallback: an inbound of some other voucher type (e.g. Sales Return).
    return _("Received ({0})").format(voucher_type), False, False
