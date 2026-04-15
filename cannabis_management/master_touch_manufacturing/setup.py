"""
Phase 6 + Phase 5 setup script for Masters Touch Manufacturing.

Run with:
    bench --site erp.alltechvirtual.com execute \
        cannabis_management.master_touch_manufacturing.setup.run
"""

import frappe

COMPANY = "Motley Terpz"
DEFAULT_RATE = 10.0  # $10/hr placeholder — update with real costs per Action Item #1


# ── helpers ────────────────────────────────────────────────────────────────

def _upsert(doctype, name_field, name_value, values: dict):
    """Create if not exists, update if it does."""
    if frappe.db.exists(doctype, name_value):
        doc = frappe.get_doc(doctype, name_value)
        for k, v in values.items():
            doc.set(k, v)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return doc
    else:
        doc = frappe.new_doc(doctype)
        doc.set(name_field, name_value)
        for k, v in values.items():
            doc.set(k, v)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc


# ── Phase 6: Workstations ─────────────────────────────────────────────────

WORKSTATIONS = [
    ("WS01", "Wash Machine",          DEFAULT_RATE, "Production"),
    ("WS02", "Rosin Press (Oven 1)",  DEFAULT_RATE, "Production"),
    ("WS03", "Rosin Press (Oven 2)",  DEFAULT_RATE, "Production"),
    ("WS04", "Freeze Dryer",          DEFAULT_RATE, "Production"),
    ("WS05", "Weigh Station",         DEFAULT_RATE, "QC"),
    ("WS06", "Decarb Oven",           DEFAULT_RATE, "Production"),
    ("WS07", "QC / Lab Station",      DEFAULT_RATE, "QC"),
    ("WS08", "Packaging",             DEFAULT_RATE, "Production"),
]


def setup_workstations():
    print("\n── Workstations ─────────────────────────────────────────────")
    for code, label, rate, ws_type in WORKSTATIONS:
        _upsert("Workstation", "workstation_name", code, {
            "workstation_name": code,
            "description": label,
            "hour_rate": rate,
            "working_hours_per_day": 8,
        })
        frappe.db.set_value("Workstation", code, "description", label)
        print(f"  OK  {code} — {label} @ ${rate}/hr")


# ── Phase 6: Operations ───────────────────────────────────────────────────

OPERATIONS = [
    # (name, workstation, description)
    ("Wash Setup",          "WS01", "Ice packing, bag setup, water temperature check"),
    ("Ice Water Wash",      "WS01", "Full ice water wash session"),
    ("Micron Filtration",   "WS01", "Drain and filter through each micron bag"),
    ("Collection & Weigh",  "WS05", "Per-bag weight entry and collection"),
    ("Freeze Dry",          "WS04", "Freeze dryer cycle — machine time"),
    ("QC & Grading",        "WS07", "Grade assignment, METRC tag, QC approval"),
    ("Press Setup",         "WS02", "Preheat rosin press, load bags, set parameters"),
    ("Press Run",           "WS02", "Active rosin press run"),
]


def setup_operations():
    print("\n── Operations ───────────────────────────────────────────────")
    for op_name, ws, desc in OPERATIONS:
        _upsert("Operation", "name", op_name, {
            "workstation": ws,
            "description": desc,
        })
        print(f"  OK  {op_name} → {ws}")


# ── Phase 6: Routings ─────────────────────────────────────────────────────

ROUTING1_OPS = [
    # (sequence_id, operation, workstation, time_in_mins)
    ("01-WASH-SETUP",    "Wash Setup",          "WS01",  30),
    ("02-WASH-RUN",      "Ice Water Wash",       "WS01", 480),
    ("03-WASH-FILTER",   "Micron Filtration",    "WS01",  60),
    ("04-WEIGH",         "Collection & Weigh",   "WS05",  45),
    ("05-FREEZE",        "Freeze Dry",           "WS04", 480),
    ("06-QC",            "QC & Grading",         "WS07",  60),
]

ROUTING2_OPS = [
    ("01-PRESS-SETUP",   "Press Setup",          "WS02",  30),
    ("02-PRESS-RUN",     "Press Run",            "WS02", 120),
    ("03-WEIGH",         "Collection & Weigh",   "WS05",  30),
    ("04-QC",            "QC & Grading",         "WS07",  45),
]


def _build_routing(name, ops_list):
    """Create or fully replace a Routing document."""
    if frappe.db.exists("Routing", name):
        doc = frappe.get_doc("Routing", name)
        doc.operations = []
    else:
        doc = frappe.new_doc("Routing")
        doc.routing_name = name

    for seq_id, op, ws, mins in ops_list:
        doc.append("operations", {
            "sequence_id": seq_id,
            "operation": op,
            "workstation": ws,
            "time_in_mins": mins,
            "hour_rate": DEFAULT_RATE,
        })

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  OK  Routing '{name}' — {len(ops_list)} operations")


def setup_routings():
    print("\n── Routings ─────────────────────────────────────────────────")
    _build_routing("Routing 1 - Fresh Frozen Wash", ROUTING1_OPS)
    _build_routing("Routing 2 - Bubble Hash Press", ROUTING2_OPS)


# ── Phase 5: Template Items ───────────────────────────────────────────────

TEMPLATE_ITEMS = [
    # (item_code, item_name, item_group, stock_uom, description)
    ("ff-template",         "Fresh Frozen — Template",         "Fresh Frozen", "LBS",  "BOM template — clone per strain"),
    ("hash-prime-template", "Bubble Hash Prime — Template",    "Primes",       "Gram", "BOM template — clone per strain"),
    ("hash-sub-template",   "Bubble Hash Subprime — Template", "Subprimes",    "Gram", "BOM template — clone per strain"),
    ("rosin-template",      "Rosin — Template",                "Rosin",        "Gram", "BOM template — clone per strain"),
]

CONSUMABLE_ITEMS = [
    ("cons-ice-water",   "Ice Water (Consumable)",           "Litre"),
    ("cons-solvent",     "Isopropyl / Ethanol (Consumable)", "Litre"),
    ("cons-bags-25u",    "Micron Bags 25μ",                  "Nos"),
    ("cons-bags-45u",    "Micron Bags 45μ",                  "Nos"),
    ("cons-bags-73u",    "Micron Bags 73μ",                  "Nos"),
    ("cons-bags-90u",    "Micron Bags 90μ",                  "Nos"),
    ("cons-bags-120u",   "Micron Bags 120μ",                 "Nos"),
    ("cons-bags-160u",   "Micron Bags 160μ",                 "Nos"),
    ("cons-bags-190u",   "Micron Bags 190μ",                 "Nos"),
    ("cons-parchment",   "Parchment Paper",                  "Nos"),
    ("cons-metrc-tag",   "METRC Tag Supply",                 "Nos"),
]


def _ensure_item(item_code, item_name, item_group, stock_uom,
                 description="", is_stock=1, valuation="FIFO",
                 has_batch=0, buy=1, sell=0):
    """Create item with name = item_code (bypasses STO-ITEM naming series via set_name)."""
    if frappe.db.exists("Item", item_code):
        print(f"  --  {item_code} (already exists)")
        return
    doc = frappe.new_doc("Item")
    doc.item_code = item_code
    doc.item_name = item_name
    doc.item_group = item_group
    doc.stock_uom = stock_uom
    doc.description = description or item_name
    doc.is_stock_item = is_stock
    doc.valuation_method = valuation
    doc.has_batch_no = has_batch
    doc.is_purchase_item = buy
    doc.is_sales_item = sell
    doc.append("item_defaults", {
        "company": COMPANY,
        "default_warehouse": "",
    })
    # set_name forces doc.name = item_code so BOM Link fields resolve correctly
    doc.insert(ignore_permissions=True, set_name=item_code)
    frappe.db.commit()
    print(f"  +   {item_code} — {item_name}")


def setup_items():
    print("\n── Template Items ───────────────────────────────────────────")
    for code, name, group, uom, desc in TEMPLATE_ITEMS:
        _ensure_item(code, name, group, uom, description=desc,
                     has_batch=1, valuation="Moving Average")

    print("\n── Consumable Items ─────────────────────────────────────────")
    for code, name, uom in CONSUMABLE_ITEMS:
        _ensure_item(code, name, "Consumable", uom,
                     description=name, is_stock=1, valuation="FIFO",
                     has_batch=0, buy=1, sell=0)


# ── Phase 5: BOMs ─────────────────────────────────────────────────────────

def _bom_insert(bom):
    """Insert BOM with ignore_links — ERPNext validate() already verifies items."""
    bom.flags.ignore_links = True
    bom.insert(ignore_permissions=True)


def setup_boms():
    print("\n── BOMs ─────────────────────────────────────────────────────")

    # BOM 1 — FF → Bubble Hash (Internal)
    if not frappe.db.exists("BOM", {"item": "hash-prime-template", "is_active": 1,
                                     "docstatus": 1, "custom_is_toll_bom": 0}):
        bom1 = frappe.new_doc("BOM")
        bom1.item = "hash-prime-template"
        bom1.quantity = 1000          # base 1000g output
        bom1.company = COMPANY
        bom1.with_operations = 1
        bom1.routing = "Routing 1 - Fresh Frozen Wash"
        bom1.custom_is_toll_bom = 0

        bom1.append("items", {"item_code": "ff-template",     "qty": 2500, "uom": "Gram",
                               "description": "Fresh Frozen input (scaled per WO)"})
        bom1.append("items", {"item_code": "cons-ice-water",  "qty": 20,   "uom": "Litre"})
        bom1.append("items", {"item_code": "cons-bags-25u",   "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-45u",   "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-73u",   "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-90u",   "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-120u",  "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-160u",  "qty": 5,    "uom": "Nos"})
        bom1.append("items", {"item_code": "cons-bags-190u",  "qty": 5,    "uom": "Nos"})

        # Scrap: subprime by-product
        bom1.append("scrap_items", {"item_code": "hash-sub-template", "stock_qty": 150,
                                     "stock_uom": "Gram", "description": "Subprime output"})

        _bom_insert(bom1)
        bom1.submit()
        frappe.db.commit()
        print(f"  +   BOM 1 (FF → Bubble Hash): {bom1.name}")
    else:
        print("  --  BOM 1 (already exists)")

    # BOM 2 — Bubble Hash → Rosin (Internal)
    if not frappe.db.exists("BOM", {"item": "rosin-template", "is_active": 1,
                                     "docstatus": 1, "custom_is_toll_bom": 0}):
        bom2 = frappe.new_doc("BOM")
        bom2.item = "rosin-template"
        bom2.quantity = 250           # base 250g rosin output
        bom2.company = COMPANY
        bom2.with_operations = 1
        bom2.routing = "Routing 2 - Bubble Hash Press"
        bom2.custom_is_toll_bom = 0

        bom2.append("items", {"item_code": "hash-prime-template", "qty": 500,  "uom": "Gram",
                               "description": "Bubble Hash Prime input"})
        bom2.append("items", {"item_code": "cons-bags-25u",       "qty": 10,   "uom": "Nos"})
        bom2.append("items", {"item_code": "cons-bags-45u",       "qty": 10,   "uom": "Nos"})
        bom2.append("items", {"item_code": "cons-parchment",      "qty": 20,   "uom": "Nos"})

        _bom_insert(bom2)
        bom2.submit()
        frappe.db.commit()
        print(f"  +   BOM 2 (Bubble Hash → Rosin): {bom2.name}")
    else:
        print("  --  BOM 2 (already exists)")

    # BOM 3 — Toll: FF → Bubble Hash
    if not frappe.db.exists("BOM", {"item": "hash-prime-template", "is_active": 1,
                                     "docstatus": 1, "custom_is_toll_bom": 1}):
        bom3 = frappe.get_doc("BOM", {"item": "hash-prime-template", "is_active": 1, "docstatus": 1})
        bom3_toll = frappe.copy_doc(bom3)
        bom3_toll.custom_is_toll_bom = 1
        bom3_toll.custom_toll_fee_g = 1.50  # placeholder $1.50/g — update per client
        for row in bom3_toll.items:
            if row.item_code == "ff-template":
                row.rate = 0
                row.amount = 0
        _bom_insert(bom3_toll)
        bom3_toll.submit()
        frappe.db.commit()
        print(f"  +   BOM 3 (Toll FF → Bubble Hash): {bom3_toll.name}")
    else:
        print("  --  BOM 3 Toll (already exists)")

    # BOM 4 — Toll: Bubble Hash → Rosin
    if not frappe.db.exists("BOM", {"item": "rosin-template", "is_active": 1,
                                     "docstatus": 1, "custom_is_toll_bom": 1}):
        bom2_doc = frappe.get_doc("BOM", {"item": "rosin-template", "is_active": 1, "docstatus": 1})
        bom4_toll = frappe.copy_doc(bom2_doc)
        bom4_toll.custom_is_toll_bom = 1
        bom4_toll.custom_toll_fee_g = 2.00  # placeholder $2.00/g — update per client
        for row in bom4_toll.items:
            if row.item_code == "hash-prime-template":
                row.rate = 0
                row.amount = 0
        _bom_insert(bom4_toll)
        bom4_toll.submit()
        frappe.db.commit()
        print(f"  +   BOM 4 (Toll Bubble Hash → Rosin): {bom4_toll.name}")
    else:
        print("  --  BOM 4 Toll (already exists)")


# ── Entry point ───────────────────────────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  MTM Phase 6 + Phase 5 Setup")
    print("="*60)
    setup_workstations()
    setup_operations()
    setup_routings()
    setup_items()
    setup_boms()
    print("\n" + "="*60)
    print("  Setup complete.")
    print("="*60 + "\n")
