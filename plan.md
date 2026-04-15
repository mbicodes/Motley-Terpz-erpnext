# Masters Touch Manufacturing × La Canna Distro
## Implementation Plan — ERPNext Module Build

**Module:** `master_touch_manufacturing` (inside `cannabis_management` app)
**App path:** `apps/cannabis_management/cannabis_management/master_touch_manufacturing/`
**Status:** Module registered in `modules.txt` ✓ | Directory scaffolded ✓ | Content: empty

---

## Phase Overview

| Phase | Name | Deliverable |
|-------|------|-------------|
| 1 | Module Scaffold | Folder structure, `__init__.py`, workspace |
| 2 | Item Master Config | Item records, naming conventions, item variants + attributes |
| 3 | Custom DocTypes | 8 new DocTypes built from scratch |
| 4 | Native DocType Extensions | Custom fields on 8 native DocTypes |
| 5 | BOMs | 4 BOMs (2 internal + 2 toll); yield threshold configured |
| 6 | Workstations, Routing & Operations | Workstations with 4-component cost formula; Routing records |
| 7 | Work Order & Job Card Automation | Hooks, auto-creation, parallel cards, clock-in/clock-out |
| 8 | Batch System | Batch lifecycle, METRC linkage, chain tracking |
| 9 | Stock Entry: Manufacture | Auto-costing, variable yield, process loss, valuation stamp |
| 10 | Quality Inspection | Native QI configured for Bubble Hash + Rosin output |
| 11 | Chart of Accounts & WIP Structure | Item-group-wise WIP accounts; HR wage linkage |
| 12 | Slack Alerts | 11 real-time Server Script webhooks |
| 13 | Email Reports | 8 scheduled jobs (EOD + weekly) |
| 14 | Roles & Permissions | 7 roles with scoped DocType access |
| 15 | Inter-Company Flow | PO ↔ SO automation, invoice settlement |
| 16 | Fixtures & Migration | Export fixtures, write patch, bench migrate |

---

## Phase 1 — Module Scaffold

**Goal:** Set up the `master_touch_manufacturing` module so Frappe recognizes it and serves its workspace.

### Files to Create

```
cannabis_management/master_touch_manufacturing/
├── __init__.py                  ← already exists
├── doctype/                     ← all custom DocTypes live here
├── report/                      ← module-specific reports
├── page/                        ← optional dashboard pages
└── workspace/
    └── masters_touch_manufacturing/
        ├── masters_touch_manufacturing.json
        └── masters_touch_manufacturing.py
```

### Steps

1. Create all subdirectories (`doctype/`, `report/`, `page/`, `workspace/`).
2. Create workspace JSON — links to all DocTypes, Work Orders, BOMs, Job Cards in one desk shortcut panel.
3. Confirm `modules.txt` already has `Master Touch Manufacturing` (it does — verified).
4. Confirm `hooks.py` does NOT need a new entry yet — workspace auto-loads from the folder.
5. Run `bench --site erp.alltechvirtual.com migrate` to register the module.

**Validation:** Module appears in ERPNext desk. Workspace loads without errors.

---

## Phase 2 — Item Master Configuration

**Goal:** Define naming conventions and required settings for every Item that flows through the manufacturing pipeline. No code — this is ERPNext data setup.

### Item Naming Conventions

| Category | Item Code Pattern | Example |
|----------|-----------------|---------|
| Fresh Frozen | `ff-{strain}` | `ff-gg4`, `ff-gelato` |
| Bubble Hash | `bubble-{strain}-{micron}` | `bubble-gg4-25u` |
| Rosin | `rosin-{strain}-{profile}` | `rosin-gg4-badder` |
| Consumables | `cons-{name}` | `cons-ice-water`, `cons-bags-25u` |
| Labor | `labor-{role}` | `labor-wash`, `labor-press` |

### Existing Grade Structure (Item Groups — DO NOT recreate)

The system already tracks quality grades as **separate Item Groups with unique item codes**. Do NOT use Item Variants / Attributes — follow the existing convention.

**Grade → Item Group mapping (confirmed from live DB, 200+ records):**
| Grade | Item Group | Item Code Prefix | UOM | Description |
|-------|-----------|-----------------|-----|-------------|
| Prime | `Primes` | `PR-XXXXX` | Gram | Top-shelf full melt / live rosin |
| Subprime | `Subprimes` | `SP-XXXXX` | Gram | Secondary grade full melt |
| Full Spec | `Full Spec` | `FS-XXXXX` | Gram | Full-spectrum (all microns combined) |
| Food Grade | `Food Grade` | `FG-XXXXX` | Gram | Lower-grade, bulk / edibles use |

**BOM output rows** reference the specific grade item code (PR-xxxx / SP-xxxx / FS-xxxx / FG-xxxx) per output stream.

**Already in the system — DO NOT recreate:**
- `FF-xxxx` → Fresh Frozen (LBS), groups: "Fresh Frozen", "Fresh Frozen - SHO", "Fresh Frozen - BHO"
- `RO-xxxx` → Rosin (Gram), group: "Rosin"
- `PR-xxxx` → Primes / Bubble Hash top grade (Gram)
- `SP-xxxx` → Subprimes / Bubble Hash secondary grade (Gram)
- `FS-xxxx` → Full Spec hash (Gram)
- `FG-xxxx` → Food Grade hash (Gram)

When a new TSBC strain arrives, add strain-specific item codes following these existing naming patterns.

### Required Item Settings (enforce on all cannabis items)

| Setting | Value | Why |
|---------|-------|-----|
| `has_batch_no` | Yes | ERPNext Batch = METRC package |
| `has_serial_no` | Yes (Bubble Hash, Rosin) | Individual jar/unit traceability |
| `is_stock_item` | Yes | All except labor service items |
| `valuation_method` | Moving Average (FF) / BOM-driven (finished goods) | Cost accuracy |
| `stock_uom` | **LBS** for Fresh Frozen · **Gram** for hash/rosin/extracts · **L** for liquids · **Nos** for consumables | Consistency |

### Items to Create (11 new records — consumables only)

> **Labor items are NOT needed.** Labor cost is calculated from workstation hourly rate (4-component formula). No `labor-wash` / `labor-press` item records.

1. Ice Water (`cons-ice-water`) — Item Group: Consumable, UOM: Litre
2. Isopropyl / Ethanol (`cons-solvent`) — Item Group: Consumable, UOM: Litre
3. Micron Bags 25μ (`cons-bags-25u`) — Item Group: Consumable, UOM: Nos
4. Micron Bags 45μ (`cons-bags-45u`) — Item Group: Consumable, UOM: Nos
5. Micron Bags 73μ (`cons-bags-73u`) — Item Group: Consumable, UOM: Nos
6. Micron Bags 90μ (`cons-bags-90u`) — Item Group: Consumable, UOM: Nos
7. Micron Bags 120μ (`cons-bags-120u`) — Item Group: Consumable, UOM: Nos
8. Micron Bags 160μ (`cons-bags-160u`) — Item Group: Consumable, UOM: Nos
9. Micron Bags 190μ (`cons-bags-190u`) — Item Group: Consumable, UOM: Nos
10. Parchment Paper (`cons-parchment`) — Item Group: Consumable, UOM: Nos
11. METRC Tag supply (`cons-metrc-tag`) — Item Group: Consumable, UOM: Nos

**Validation:** All consumables: `is_stock_item = Yes`, FIFO valuation, `has_batch_no = No`.

---

## Phase 3 — Custom DocTypes (Build from Scratch)

All DocTypes live in:
`cannabis_management/master_touch_manufacturing/doctype/{doctype_name}/`

Each folder contains: `{name}.json` + `{name}.py` + `{name}.js`

---

### 3.1 — Production Batch Group

**Purpose:** Master job folder. Parent record for an entire production run from FF receipt through finished goods.

**File:** `doctype/production_batch_group/production_batch_group.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `batch_group_id` | Data (auto) | ✓ | Naming series: `PBG-{YYYY}-{WW}-{###}` |
| `batch_name` | Data | ✓ | Human label: `GG4 — Week 22 — 1000 lbs` |
| `strain_name` | Link → Item | ✓ | FF item code |
| `source_entity` | Link → Supplier | ✓ | TSBC Farms (or toll customer) |
| `ff_weight_received_lbs` | Float | ✓ | Total lbs received |
| `ff_weight_received_g` | Float (read-only) | — | Auto: `lbs × 453.592` (controller) |
| `purchase_receipt_ref` | Link → Purchase Receipt | ✓ | Inbound receipt |
| `work_order_ref` | Link → Work Order | ✓ | Driving WO |
| `wash_batches` | Child Table → Wash Batch | ✓ | All wash runs in this group |
| `press_batches` | Child Table → Press Batch | ✓ | All press runs |
| `erpnext_batches` | Child Table → Batch | ✓ | All ERPNext Batch records created |
| `status` | Select | ✓ | Open / In Wash / In Press / Inventory Verification / Closed |
| `total_bubble_yield_g` | Float (read-only) | — | Sum of wash batch yields (controller) |
| `total_rosin_yield_g` | Float (read-only) | — | Sum of press batch yields (controller) |
| `ff_to_bubble_yield_pct` | Percent (read-only) | — | `(bubble_g / ff_g) × 100` |
| `bubble_to_rosin_yield_pct` | Percent (read-only) | — | `(rosin_g / bubble_g) × 100` |
| `total_material_cost` | Currency (read-only) | — | Pulled from WO actual |
| `total_labor_cost` | Currency (read-only) | — | Sum of Job Card actual costs |
| `total_overhead_cost` | Currency (read-only) | — | Machine time costs |
| `cost_per_gram_bubble` | Currency (read-only) | — | `total_cost / bubble_g` |
| `cost_per_gram_rosin` | Currency (read-only) | — | `total_cost / rosin_g` |
| `notes` | Text | — | Free-form |

**Controller logic (`production_batch_group.py`):**
- `before_save`: auto-convert lbs → g
- `on_update`: recalculate all yield %, cost per gram rollups by summing child Wash/Press Batches
- Naming series hook → auto-generate `PBG-{YYYY}-{WW}-{###}`

---

### 3.2 — Wash Batch

**Purpose:** Captures all data from a single wash session (one Job Card at Wash Station).

**File:** `doctype/wash_batch/wash_batch.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `wash_batch_id` | Data (auto) | ✓ | Naming: `WB-{YYYY}-{####}` |
| `production_batch_group` | Link → Production Batch Group | ✓ | Parent run |
| `work_order` | Link → Work Order | ✓ | Associated WO |
| `job_card` | Link → Job Card | ✓ | Associated Job Card |
| `wash_date` | Date | ✓ | Date wash was performed |
| `strain_name` | Link → Item | ✓ | FF strain |
| `ff_input_g` | Float | ✓ | Grams of FF going in |
| `wash_tech` | Link → Employee | ✓ | Who ran the wash |
| `wash_details` | Child Table → Wash Detail | ✓ | Per-cycle, per-micron rows |
| `total_bubble_yield_g` | Float (read-only) | — | Sum of wash_details.grams_collected |
| `yield_pct` | Percent (read-only) | — | `(yield_g / ff_input_g) × 100` |
| `status` | Select | ✓ | Open / In Progress / Complete |
| `notes` | Text | — | Batch notes |

---

### 3.3 — Wash Detail (Child Table)

**Purpose:** One row per wash cycle per micron bag. Live entry during washing.

**File:** `doctype/wash_detail/wash_detail.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `wash_number` | Int | ✓ | Cycle number (1, 2, 3…) |
| `micron_size` | Select | ✓ | 25 / 45 / 73 / 90 / 120 / 160 / 190 |
| `grams_collected` | Float | ✓ | Weight per bag per cycle |
| `metrc_tag_bubble` | Data | ✓ | METRC tag for this package |
| `quality_grade` | Select | ✓ | Full Melt / 4-Star / 3-Star / 2-Star / Food Grade |
| `collected_by` | Link → Employee | ✓ | Person collecting at this station |
| `collection_time` | Datetime | ✓ | Timestamp of collection |
| `erpnext_batch` | Link → Batch | — | ERPNext Batch record auto-created on row save |

---

### 3.4 — Press Batch

**Purpose:** Captures all data from a single rosin press session.

**File:** `doctype/press_batch/press_batch.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `press_batch_id` | Data (auto) | ✓ | Naming: `PB-{YYYY}-{####}` |
| `production_batch_group` | Link → Production Batch Group | ✓ | Parent run |
| `work_order` | Link → Work Order | ✓ | Associated WO |
| `job_card` | Link → Job Card | ✓ | Associated Job Card |
| `press_date` | Date | ✓ | Date pressed |
| `strain_name` | Link → Item | ✓ | Strain |
| `bubble_hash_input_g` | Float | ✓ | Grams of bubble hash going in |
| `source_wash_batch` | Link → Wash Batch | ✓ | Which wash batch was pressed |
| `press_tech` | Link → Employee | ✓ | Who ran the press |
| `workstation` | Link → Workstation | ✓ | WS-PRESS-01 or WS-PRESS-02 |
| `press_details` | Child Table → Press Detail | ✓ | Per-press-run rows |
| `total_rosin_yield_g` | Float (read-only) | — | Sum of press_details.grams_rosin |
| `yield_pct` | Percent (read-only) | — | `(rosin_g / bubble_g) × 100` |
| `discrepancy_g` | Float (read-only) | — | `bubble_input - rosin_yield - chips` |
| `discrepancy_resolved` | Check | — | Required if discrepancy ≠ 0 |
| `discrepancy_notes` | Text | — | Required if discrepancy_resolved = 1 |
| `status` | Select | ✓ | Open / In Progress / Complete |

---

### 3.5 — Press Detail (Child Table)

**Purpose:** One row per press run per rosin profile. Live entry at press station.

**File:** `doctype/press_detail/press_detail.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `micron_bag_size` | Select | ✓ | 25 / 36 / 45 / 72 |
| `press_temp_f` | Float | ✓ | Temperature in °F |
| `press_pressure_psi` | Float | ✓ | PSI applied |
| `press_duration_sec` | Int | ✓ | Duration in seconds |
| `grams_rosin` | Float | ✓ | Yield per press run |
| `metrc_tag_rosin` | Data | ✓ | METRC tag for this rosin package |
| `color_grade` | Select | ✓ | Light Amber / Amber / Dark Amber / Green |
| `consistency` | Select | ✓ | Badder / Sauce / Shatter / Jam / Live Rosin |
| `pressed_by` | Link → Employee | ✓ | Person pressing |
| `erpnext_batch` | Link → Batch | — | Auto-created on row save |

---

### 3.6 — Inventory Verification

**Purpose:** Second-person physical count before releasing batches into live inventory.

**File:** `doctype/inventory_verification/inventory_verification.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `verification_id` | Data (auto) | ✓ | Naming: `IV-{YYYY}-{####}` |
| `production_batch_group` | Link → Production Batch Group | ✓ | |
| `verification_type` | Select | ✓ | Bubble Hash / Rosin |
| `source_batch_ref` | Link → Wash Batch / Press Batch | ✓ | What is being verified |
| `verified_by` | Link → Employee | ✓ | Must NOT be the wash/press tech |
| `verification_date` | Date | ✓ | |
| `metrc_packages` | Child Table → METRC Package Verification | ✓ | Per-tag weight rows |
| `system_total_g` | Float (read-only) | — | Total from ERPNext batches |
| `physical_total_g` | Float (read-only) | — | Sum of metrc_packages.verified_g |
| `variance_g` | Float (read-only) | — | `system - physical` |
| `variance_pct` | Percent (read-only) | — | |
| `variance_resolution` | Text | — | Required if variance_g ≠ 0 |
| `approved_for_inventory` | Check | ✓ | Locks batch as released when checked |
| `approved_by` | Link → Employee | — | Auto-set on approval |
| `approved_date` | Datetime | — | Auto-set on approval |

**Validation:** `verified_by` cannot equal the wash/press tech on the source batch. Enforced in controller.

---

### 3.7 — METRC Package Verification (Child Table)

**File:** `doctype/metrc_package_verification/metrc_package_verification.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `metrc_tag` | Data | ✓ | |
| `erpnext_batch` | Link → Batch | ✓ | |
| `system_weight_g` | Float (read-only) | — | Pulled from Batch.net_weight_g |
| `verified_weight_g` | Float | ✓ | Physical scale reading |
| `variance_g` | Float (read-only) | — | Auto-calc |

---

### 3.8 — METRC Retag Log (Child Table)

**Purpose:** Records new METRC tags applied when FF arrives at lab.

**File:** `doctype/metrc_retag_log/metrc_retag_log.json`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `original_tag` | Data | ✓ | Tag from TSBC Farms |
| `new_tag` | Data | ✓ | New MTM facility tag |
| `strain` | Data | ✓ | |
| `weight_g` | Float | ✓ | Weight on new tag |
| `retagged_by` | Link → Employee | ✓ | |
| `retag_datetime` | Datetime | ✓ | |

---

## Phase 4 — Custom Fields on Native DocTypes

These are added via **fixtures** (exported as `Custom Field` JSON) so they survive bench updates.

**Fixture file:** `cannabis_management/fixtures/custom_field.json` (append to existing)

---

### 4.1 — Purchase Receipt

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `production_batch_group` | Link → Production Batch Group | Production Batch Group | Section break above |
| `metrc_tag_original` | Data | Original METRC Tag | From TSBC Farms |
| `weight_sent_g` | Float | Weight Sent (g) | What TSBC says they sent |
| `weight_received_g` | Float | Weight Received (g) | Actual scale at lab |
| `weight_variance_g` | Float (read-only) | Weight Variance (g) | Auto: sent − received |
| `weight_verified_by` | Link → Employee | Verified By | Person at scale |
| `weight_verified_date` | Date | Verified Date | |
| `custom_retag_log` | Table → METRC Retag Log | METRC Retag Log | Child table |

---

### 4.2 — Work Order

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `production_batch_group` | Link → Production Batch Group | Production Batch Group | |
| `toll_customer` | Link → Customer | Toll Customer | Blank = internal |
| `toll_job_type` | Select | Job Type | Internal / Third Party |
| `customer_material_batch` | Data | Customer Material METRC Tag | Required if Third Party |

---

### 4.3 — Job Card

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `production_batch_group` | Link → Production Batch Group | Production Batch Group | |
| `wash_batch_ref` | Link → Wash Batch | Wash Batch | For wash station cards |
| `press_batch_ref` | Link → Press Batch | Press Batch | For press station cards |
| `station_notes` | Text | Station Notes | Open notes field |

---

### 4.4 — Stock Entry

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `production_batch_group` | Link → Production Batch Group | Production Batch Group | |
| `erpnext_batch_created` | Link → Batch | Finished Goods Batch | Auto-linked on Manufacture entry |
| `metrc_manifest_number` | Data | METRC Manifest # | Required for Transfer entries |
| `manifest_uploaded` | Check | Manifest Uploaded | Must check before physical move |
| `physical_movement_date` | Date | Physical Movement Date | |
| `physical_moved_by` | Link → Employee | Moved By | |
| `third_party_destination` | Data | Third-Party Destination | If transferring outside ERPNext companies |

---

### 4.5 — Batch (Item Batch)

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `metrc_tag` | Data | METRC Tag | Unique. Validated on save. |
| `metrc_license_source` | Link → Warehouse | License Source | Which facility |
| `strain_name` | Link → Item | Strain | |
| `batch_type` | Select | Batch Type | Fresh Frozen / Bubble Hash / Rosin / Packaged / Waste |
| `source_batch` | Link → Batch | Source Batch | Parent batch (traceability chain) |
| `production_batch_group` | Link → Production Batch Group | Batch Group | |
| `wash_batch_ref` | Link → Wash Batch | Wash Batch | |
| `press_batch_ref` | Link → Press Batch | Press Batch | |
| `work_order_ref` | Link → Work Order | Work Order | |
| `gross_weight_g` | Float | Gross Weight (g) | Including packaging |
| `net_weight_g` | Float | Net Weight (g) | Usable product |
| `quality_grade` | Select | Quality Grade | Full Melt / 4-Star / 3-Star / 2-Star / Food Grade |
| `batch_status` | Select | Batch Status | Active / Quarantine / Released / Transferred / Consumed / Disposed |
| `qc_approved_by` | Link → Employee | QC Approved By | |
| `qc_approved_date` | Date | QC Approved Date | |
| `metrc_last_synced` | Datetime | METRC Last Synced | |

---

### 4.6 — Warehouse

| Field Name | Type | Label |
|------------|------|-------|
| `metrc_license_number` | Data | METRC License # |
| `license_type` | Data | License Type |
| `physical_address` | Text | Physical Address |
| `compliance_contact` | Link → Employee | Compliance Contact |

---

### 4.7 — BOM

| Field Name | Type | Label | Notes |
|------------|------|-------|-------|
| `is_toll_bom` | Check | Toll BOM | If checked: FF raw material posts at $0 |
| `toll_fee_g` | Currency | Toll Fee per Gram | Per-gram processing fee for billing |

---

### 4.8 — Stock Reconciliation

| Field Name | Type | Label |
|------------|------|-------|
| `variance_reason` | Select | Variance Reason |
| `metrc_correction_made` | Check | METRC Correction Made |
| `compliance_notes` | Text | Compliance Notes |

---

## Phase 5 — Bills of Materials (4 BOMs)

Created in ERPNext via UI or fixture. All have `with_operations = 1`.

### BOM 1 — FF → Bubble Hash (Internal)

- **Finished item:** `bubble-{strain}-prime` (primary output — highest grade variant)
- **Base qty:** 1000g
- **Raw materials:** FF, ice water, bags (all 7 microns), solvent, parchment
- **By-products (scrap_items):** Bubble Hash variants by grade at respective values; Spent Material at $0
- **Operations:** Wash Setup, Ice Water Wash, Micron Filtration, Collection & Weigh, Freeze Dry, QC & Grading
- **Workstations:** WS01 (Wash Machine) × cycles, WS-FREEZE, WS-QC, WS-WEIGH

### Yield Threshold & Variable Output Handling

> **Decision from session:** Yield is variable — some batches hit 39%, others exceed 80%. ERPNext must support this without requiring a new BOM per batch.

**How to handle in ERPNext:**
- BOM `quantity` field = 1000g base. BOM raw material quantities are expressed as `qty_per_unit` ratios — they scale automatically to whatever the Work Order planned qty is.
- Set `expected_yield_pct` as a custom field on the BOM (or Work Order). **Agreed threshold: 2.5% minimum for bubble hash.**
- On the Work Order, set `qty` (planned output) as a conservative estimate. Actual output is entered on the Stock Entry: Manufacture `fg_completed_qty` field — this can differ from planned.
- ERPNext will flag the variance between `planned_qty` and `produced_qty` automatically on the Work Order.
- The Production Batch Group calculates real yield % from actual grams, not BOM standard.

**Validation rule (controller):** If `actual_yield_pct < 2.5` (bubble hash) or `actual_yield_pct < 1.0` (rosin), block Manufacture Stock Entry submit and require a `yield_variance_reason` field entry + Lab Supervisor approval.

### BOM 2 — Bubble Hash → Rosin (Internal)

- **Finished item:** `rosin-{strain}-prime` (primary)
- **Base qty:** 500g bubble hash input
- **Raw materials:** Bubble Hash (variant linked), parchment, rosin bags (25μ, 36μ, 45μ, 72μ), spatulas
- **Scrap:** Rosin chips / spent bags at $0
- **Operations:** Press Setup, Press Run, Collection & Weigh, QC & Grading, Packaging (optional)
- **Workstations:** WS02 (Rosin Press), WS-WEIGH, WS-QC, WS-PACK

### BOM 3 — Toll Variant: FF → Bubble Hash (Third-Party)

- Identical structure to BOM 1
- `is_toll_bom = 1`
- FF raw material line: set valuation rate = $0 in BOM (customer owns it)
- `toll_fee_g` = fee charged per gram (invoiced to customer via inter-company or direct invoice)

### BOM 4 — Toll Variant: Bubble Hash → Rosin (Third-Party)

- Identical structure to BOM 2
- `is_toll_bom = 1`
- Bubble Hash input at $0 (customer material)

**Note:** BOMs should be versioned. Never delete old BOMs — deactivate and create a new version when strain/process changes. Each new strain is a new BOM (clone existing, change the FF item link).

---

## Phase 6 — Workstations, Routing & Operations

Created in ERPNext under **Manufacturing → Setup → Workstation**.

### Workstation Naming Convention

> **Decision from session:** Use sequential numeric codes — `WS01`, `WS02`, etc. — matching physical machine labels in the lab. This ties ERPNext records directly to labeled equipment.

| Code | Machine / Station | Type |
|------|------------------|------|
| WS01 | Wash Machine | Production |
| WS02 | Rosin Press (Oven 1) | Production |
| WS03 | Rosin Press (Oven 2) | Production |
| WS04 | Freeze Dryer | Production |
| WS05 | Weigh Station | QC |
| WS06 | Decarb Oven | Production |
| WS07 | QC / Lab Station | QC |
| WS08 | Packaging | Production |

### Workstation Hour Rate — 4-Component Cost Formula

> **Decision from session:** Each workstation's `hour_rate` in ERPNext is NOT a single flat number. It is the sum of four real cost components. Finalize these numbers with Usman / Huzaifa (see Action Items).

```
Hour Rate = Electricity + Consumable Amortization + Rent Allocation + Wages

Where:
  Electricity       = machine kWh/hr × $/kWh
  Consumable Amort. = monthly consumable spend for this station ÷ monthly operating hours
  Rent Allocation   = (monthly rent ÷ 4 machines) ÷ monthly operating hours per machine
  Wages             = not in workstation rate — linked separately via HR (see Phase 11)

Placeholder rate agreed for testing: $10.00/hr (to be replaced with real numbers)
```

**How to configure in ERPNext Workstation:**
- `hour_rate` field = Electricity + Consumable + Rent components only
- Labor (wages) is captured separately per Job Card via `Employee` → `Salary Structure` → wage rate pulled at Job Card close
- This split gives you machine cost vs. labor cost as separate line items on the Work Order

### Workstation Cost Finalization Checklist (Pending — Action Item #1)

| Station | Electricity ($/hr) | Consumable ($/hr) | Rent ($/hr) | Placeholder Total |
|---------|--------------------|------------------|-------------|-------------------|
| WS01 — Wash Machine | TBD | TBD | TBD | $10.00 |
| WS02 — Rosin Press 1 | TBD | TBD | TBD | $10.00 |
| WS03 — Rosin Press 2 | TBD | TBD | TBD | $10.00 |
| WS04 — Freeze Dryer | TBD | TBD | TBD | $10.00 |
| WS05 — Weigh Station | TBD | TBD | TBD | $10.00 |
| WS07 — QC / Lab | TBD | TBD | TBD | $10.00 |
| WS08 — Packaging | TBD | TBD | TBD | $10.00 |

### Routing

ERPNext **Routing** is a reusable sequence of Operations that can be applied to multiple BOMs. Create one Routing per production pathway.

> **Decision from session:** Routing created for the Wash operation first. Extend to all operations before going live.

**Routing 1 — Fresh Frozen Wash**

| Sequence ID | Operation | Workstation | Default Time (min) | Notes |
|-------------|-----------|-------------|---------------------|-------|
| 01-WASH-SETUP | Wash Setup | WS01 | 30 | Ice packing, bag setup, water temp |
| 02-WASH-RUN | Ice Water Wash | WS01 | 480 | Full 8-hour wash session default |
| 03-WASH-FILTER | Micron Filtration | WS01 | 60 | Draining through each micron bag |
| 04-WEIGH | Collection & Weigh | WS05 | 45 | Per-bag weight entry |
| 05-FREEZE | Freeze Dry / Dry | WS04 | 480 | Machine time — 8-hr default |
| 06-QC | QC & Grading | WS07 | 60 | Grade, METRC tag assignment |

**Routing 2 — Bubble Hash Press**

| Sequence ID | Operation | Workstation | Default Time (min) | Notes |
|-------------|-----------|-------------|---------------------|-------|
| 01-PRESS-SETUP | Press Setup | WS02 | 30 | Preheat, bag load, param setup |
| 02-PRESS-RUN | Press Run | WS02 | 120 | Actual press — variable by batch |
| 03-WEIGH | Collection & Weigh | WS05 | 30 | Parchment collection + scale |
| 04-QC | QC & Grading | WS07 | 45 | Grade, consistency, METRC tag |

> **Note on Operation Time — Fixed vs. Clock-In/Clock-Out:**
> The `time_in_mins` on the Operation/Routing is the **standard time** (BOM cost baseline). Actual time is captured by the technician starting and stopping the Job Card time log (clock-in/clock-out). ERPNext uses actual time from time logs for real cost — the standard time is only used for scheduling and variance reporting. Both are needed.

### Operations (Manufacturing → Setup → Operation)

Create one Operation record per unique operation name. The same Operation can appear in multiple Routings and BOMs.

---

## Phase 7 — Work Order & Job Card Automation

### Hooks to Add in `hooks.py`

```python
doc_events = {
    # ... existing hooks ...

    "Work Order": {
        "on_submit":   "cannabis_management.master_touch_manufacturing.overrides.work_order.on_submit",
        "on_update":   "cannabis_management.master_touch_manufacturing.overrides.work_order.on_update",
    },
    "Job Card": {
        "on_submit":   "cannabis_management.master_touch_manufacturing.overrides.job_card.on_submit",
        "on_update":   "cannabis_management.master_touch_manufacturing.overrides.job_card.on_update",
    },
    "Purchase Receipt": {
        "on_submit":   "cannabis_management.master_touch_manufacturing.overrides.purchase_receipt.on_submit",
    },
    "Stock Entry": {
        # append — existing validate hook stays
        "on_submit":   "cannabis_management.master_touch_manufacturing.overrides.stock_entry.on_submit",
    },
    "Inventory Verification": {
        "on_update":   "cannabis_management.master_touch_manufacturing.overrides.inventory_verification.on_update",
    },
    "Wash Batch": {
        "on_update":   "cannabis_management.master_touch_manufacturing.overrides.wash_batch.on_update",
    },
    "Press Batch": {
        "on_update":   "cannabis_management.master_touch_manufacturing.overrides.press_batch.on_update",
    },
}
```

### Job Card Behavior — Key Decisions from Session

> **Confirmed in testing:** Submitting a Job Card does NOT complete the Work Order. The Work Order moves to "Completed" only when a **Stock Entry: Manufacture** is submitted against it. This is by design — the Job Card captures labor/machine time, the Stock Entry captures actual material consumption and finished goods creation.

**Parallel Job Cards:**
Multiple workstations can run Job Cards simultaneously against the same Work Order. For example, WS01 (Wash) and WS04 (Freeze Dryer) can have open Job Cards at the same time. ERPNext handles this natively — each Job Card is independent. Track utilization by Workstation in the EOD Work Order Summary report.

**Job Card Fields Used (confirmed in testing):**
- `employee` — who is at the station
- `time_logs` — start/end time entries (clock-in/clock-out). Multiple sessions per card allowed.
- `total_completed_qty` — grams processed at this station (for progress tracking, not inventory)
- `actual_operating_cost` — auto-calculated: `total_time_in_mins × workstation.hour_rate / 60`

**Clock-In / Clock-Out vs. Fixed Time:**
- Standard time in BOM/Routing = scheduling baseline and BOM cost standard
- Actual time = sum of `time_logs` sessions on the Job Card → used for real cost
- Both are visible on the Work Order cost analysis tab after completion

**Tested in session:** 50 units processed in 77 seconds. ERPNext logged the time correctly and calculated `actual_operating_cost` automatically. Job Card submitted without errors.

### Automation Logic

**`overrides/work_order.py`**
- `on_submit`: Create a Production Batch Group if none linked. Set status = "Open".
- `on_update`: When status changes to "In Progress" → send Slack alert to `#lab-ops`. When status = "Completed" → rollup actual costs to Production Batch Group, send Slack summary.

**`overrides/job_card.py`**
- `on_submit`: When Job Card for a Wash Station (WS01) is submitted → trigger Wash Batch status = "Complete". Same for Press Station (WS02/WS03) → Press Batch.
- `on_update`: Update `actual_operating_cost` on the linked Wash/Press Batch. Also update `production_batch_group.total_labor_cost` running total.

**`overrides/purchase_receipt.py`**
- `on_submit`: Validate `weight_variance_g`. If ≠ 0, send Slack alert to `#lab-alerts`. Block submit if unresolved variance field is empty.

**`overrides/wash_batch.py`**
- `on_update`: When `status = "Complete"` → recalculate `total_bubble_yield_g`, `yield_pct`. Update parent Production Batch Group totals. Fire Slack alert to `#lab-ops`.

**`overrides/press_batch.py`**
- `on_update`: When `status = "Complete"` → recalculate `total_rosin_yield_g`, `yield_pct`. Check `discrepancy_g`. If ≠ 0 and `discrepancy_resolved = 0`, raise validation error + send Slack to `#lab-alerts`. Update parent Production Batch Group.

**`overrides/inventory_verification.py`**
- `on_update`: Validate `verified_by ≠` wash/press tech on source batch. When `approved_for_inventory = 1` → set all linked Batch records to `batch_status = "Released"`. Update Production Batch Group status.

**`overrides/stock_entry.py` (append, Manufacturing type only)**
- `on_submit` where `stock_entry_type = "Manufacture"`: auto-link `production_batch_group` from Work Order. Auto-set `erpnext_batch_created` from the target item row's batch. Send Slack transfer alert if `stock_entry_type = "Material Transfer"` and `manifest_uploaded = 1`.

### Batch Sequence Lock

Server Script (or `overrides/production_batch_group.py`):
- Before a new Production Batch Group can be submitted for a given strain/entity, check that no prior PBG for that entity has `status != "Closed"`. If blocked → raise error + Slack to `#lab-alerts`.

---

## Phase 8 — Batch System

### Auto-Creation Logic

Batches are created automatically at two points:

1. **Purchase Receipt submit** → one Batch per METRC Retag Log row (FF batches)
   - `batch_type = "Fresh Frozen"`, `metrc_tag` = new tag from retag log, `strain_name` = from receipt
   - `batch_status = "Active"`, `source_batch = null`

2. **Wash Detail / Press Detail row save** → one Batch per row
   - Wash Detail: `batch_type = "Bubble Hash"`, `source_batch` = FF batch consumed, `wash_batch_ref` = parent Wash Batch
   - Press Detail: `batch_type = "Rosin"`, `source_batch` = Bubble Hash batch pressed, `press_batch_ref` = parent Press Batch

### Batch Chain Traceability

Every finished goods Batch has `source_batch` → pointing to the input batch. This creates a full chain:

```
FF Batch (from TSBC PO)
  └── Bubble Hash Batch (from Wash Detail row)
        └── Rosin Batch (from Press Detail row)
```

Full chain is traversable via Link fields. Add a timeline/graph view to the Production Batch Group workspace page.

### METRC Sync Field

`metrc_last_synced` on Batch is updated by the daily reconciliation scheduled job. If `metrc_last_synced` is > 24h old and `batch_status = "Active"`, flag in the EOD Inventory Snapshot report.

---

## Phase 9 — Stock Entry: Manufacture

### On Submit Logic

When a `Stock Entry` of type `Manufacture` is submitted referencing a `work_order` that has `production_batch_group`:

1. Compute actual cost: `sum(source item rows at actual valuation) + sum(Job Card actual_operating_cost)`
2. Divide by `fg_completed_qty` → `cost_per_gram`
3. Stamp `cost_per_gram` as the valuation rate on the finished goods Batch
4. Write `cost_per_gram_bubble` or `cost_per_gram_rosin` back to Production Batch Group
5. Auto-set `erpnext_batch_created` = the target row's batch number
6. If `process_loss` > 0 → post to manufacturing loss account (configured in Company defaults)

### Toll BOM Cost Handling

If `bom.is_toll_bom = 1`:
- Override FF / Bubble Hash valuation rate to $0 on manufacture entry source rows
- Only labor + consumable rows carry actual cost
- `toll_fee_g` from BOM is used to generate the toll invoice line item

---

## Phase 10 — Quality Inspection

> **Decision from session:** ERPNext's native Quality Inspection (QI) DocType is used for validating bubble hash and rosin output before inventory release. This replaces a manual process and links to the Inventory Verification step.

### Configuration

**Enable Quality Inspection in ERPNext:**
- Manufacturing Settings → `Inspection Required Before Transfer` = No (we inspect at manufacture, not transfer)
- Manufacturing Settings → `Inspection Required Before Delivery` = Yes (optional — for distro)
- Item Master → each cannabis output item: set `inspection_required = 1`

**Quality Inspection Template — Bubble Hash**

| Parameter | Acceptable Range | Method |
|-----------|-----------------|--------|
| Net Weight (g) | Within 2% of METRC package tag weight | Scale |
| Moisture Content | < 15% | Visual / moisture meter |
| Color Grade | Full Melt / 4-Star / 3-Star / Food Grade | Visual |
| Contamination | None visible | Visual |
| METRC Tag Match | Exact match to batch record | Manual check |

**Quality Inspection Template — Rosin**

| Parameter | Acceptable Range | Method |
|-----------|-----------------|--------|
| Net Weight (g) | Within 1% of press detail record | Scale |
| Color Grade | Light Amber / Amber / Dark Amber / Green | Visual |
| Consistency | Matches declared profile (Badder/Sauce/etc.) | Visual |
| Terpene Aroma | Acceptable (no off-notes) | Sensory |
| METRC Tag Match | Exact match | Manual check |

### Linking QI to Inventory Verification

- When an `Inventory Verification` record is saved with `approved_for_inventory = 1`, auto-create a Quality Inspection record for each batch
- QI status must = "Accepted" before `batch_status` can be set to "Released"
- Add `quality_inspection_ref` as a custom Link field on the `Batch` DocType (see Phase 4.5)

### Item Variant × Grade

The QI result determines which **item variant** the batch is assigned to:
- QI passes Full Melt criteria → batch assigned to `bubble-{strain}-prime`
- QI passes 3-Star criteria → batch assigned to `bubble-{strain}-distillate`
- QI passes Food Grade criteria → batch assigned to `bubble-{strain}-food-grade`

This grade assignment happens in `overrides/inventory_verification.py` when QI is accepted.

---

## Phase 11 — Chart of Accounts & WIP Structure

> **Decision from session:** Work In Progress (WIP) accounts must be structured **item-group-wise** — not a single generic WIP account. This enables accurate cost tracking per product category and cleaner financial reporting.

### WIP Account Structure (Chart of Accounts — MTM Company)

```
1400 — Work In Progress (Group)
  ├── 1401 — WIP — Fresh Frozen Processing
  ├── 1402 — WIP — Bubble Hash Production
  ├── 1403 — WIP — Rosin Production
  └── 1404 — WIP — Toll Manufacturing

1300 — Finished Goods Inventory (Group)
  ├── 1301 — Inventory — Bubble Hash
  ├── 1302 — Inventory — Rosin
  └── 1303 — Inventory — Packaged Products
```

**How to link Item Groups to WIP accounts in ERPNext:**
- Item Group → `default_expense_account` → map each cannabis item group to its WIP account
- When a Stock Entry: Manufacture posts, ERPNext uses the Item Group's account mapping to debit/credit the correct WIP account automatically

### HR Wage Linkage to Workstations

> **Decision from session:** Employee wages must be linked to specific workstations at the time of Job Card creation — not a flat rate on the workstation itself. This allows different employees at the same station to cost at their actual wage.

**Implementation:**

1. In ERPNext Employee record → add custom field: `default_workstation` (Link → Workstation). Set at employee creation.
2. On Job Card `on_create` hook: if `employee` is set, auto-populate `workstation` from `employee.default_workstation` (if not already set by WO routing).
3. Wage rate source: `Salary Structure Assignment` for the employee → get `base` salary → divide by monthly hours → derive hourly rate.
4. `actual_operating_cost` on Job Card = `total_time_in_mins / 60 × employee_hourly_rate` (labor) + `total_time_in_mins / 60 × workstation.hour_rate` (machine/overhead).

**Custom field to add on Employee (Phase 4 fixture):**

| Field | Type | Label |
|-------|------|-------|
| `default_workstation` | Link → Workstation | Default Workstation |
| `hourly_wage_rate` | Currency | Hourly Wage Rate |

> Set `hourly_wage_rate` manually or auto-derive from Salary Structure. Manual is simpler for now — revisit when payroll is fully configured.

### Manufacturing Overhead Account

Set a dedicated overhead account in Company defaults:
- `Manufacturing Overhead → Account: 5100 — Manufacturing Overhead`
- ERPNext posts machine cost (workstation hour_rate × time) here automatically on Job Card submit

---

## Phase 12 — Slack Alerts

**Location:** ERPNext → Server Scripts (DocType Event type) OR `overrides/*.py` via `requests.post()`

**Webhook URLs:** Configured per channel in `site_config.json` under custom keys:
```json
{
  "slack_webhook_lab_ops": "https://hooks.slack.com/services/...",
  "slack_webhook_lab_alerts": "https://hooks.slack.com/services/...",
  "slack_webhook_distro_ops": "https://hooks.slack.com/services/...",
  "slack_webhook_compliance": "https://hooks.slack.com/services/..."
}
```

**Helper:** `master_touch_manufacturing/utils/slack.py`
```python
def send_slack(channel_key: str, message: str): ...
```

### 11 Alerts to Implement

| # | Alert | Trigger | Channel | Priority |
|---|-------|---------|---------|----------|
| 1 | Fresh Frozen Received | Purchase Receipt → on_submit | #lab-ops | Info |
| 2 | Wash Batch Complete | Wash Batch → status = Complete | #lab-ops | Info |
| 3 | Rosin Press Complete | Press Batch → status = Complete | #lab-ops | Info |
| 4 | Weight Variance — Receipt | Purchase Receipt → save (variance ≠ 0) | #lab-alerts | Urgent |
| 5 | Press Weight Discrepancy | Press Batch → save (discrepancy ≠ 0) | #lab-alerts | Flag |
| 6 | Inventory Variance | Inventory Verification → save (variance ≠ 0) | #lab-alerts | Flag |
| 7 | Batch Sequence Lock | PBG → create (prior open) | #lab-alerts | Blocked |
| 8 | Work Order Started | Work Order → In Progress | #lab-ops | Info |
| 9 | Work Order Complete | Work Order → Completed | #lab-ops | Summary |
| 10 | Transfer Initiated | Stock Entry Transfer → submit | #distro-ops | Info |
| 11 | 3-Way Sync Discrepancy | Daily reconciliation job | #compliance-alerts | Urgent |

**All alert messages include:** batch group ID, strain, tech name, timestamp, and key metric (weight, yield %, variance).

---

## Phase 13 — Email Reports (Scheduled Jobs)

**Location:** `hooks.py` `scheduler_events` + `master_touch_manufacturing/tasks.py`

### Add to `hooks.py`

```python
scheduler_events = {
    "daily": [
        # ... existing ...
        "cannabis_management.master_touch_manufacturing.tasks.eod_bubble_hash_report",
        "cannabis_management.master_touch_manufacturing.tasks.eod_rosin_report",
        "cannabis_management.master_touch_manufacturing.tasks.eod_work_order_summary",
        "cannabis_management.master_touch_manufacturing.tasks.eod_inventory_snapshot",
        "cannabis_management.master_touch_manufacturing.tasks.eod_cost_summary",
    ],
    "weekly": [
        "cannabis_management.master_touch_manufacturing.tasks.weekly_batch_group_report",
        "cannabis_management.master_touch_manufacturing.tasks.weekly_3way_reconciliation",
    ],
}
```

### 8 Reports to Implement

| # | Report | Schedule | Recipients | Key Data |
|---|--------|----------|------------|---------|
| 1 | EOD Bubble Hash Report | Daily 23:59 | Ops Team | All wash batches today — strain, grams, yield %, tech, status |
| 2 | EOD Rosin Report | Daily 23:59 | Ops Team | All press batches today — same columns |
| 3 | EOD Work Order Summary | Daily 23:59 | Management | Active WOs — WO#, PBG, strain, planned vs produced, % complete, days open |
| 4 | EOD Inventory Snapshot | Daily 23:59 | Management | ERPNext stock LAB + DISTRO. Flag if METRC not synced today |
| 5 | EOD Cost Summary | Daily 23:59 | Management | Manufacture entries today — actual cost, cost/gram, vs BOM standard, variance |
| 6 | Weekly Batch Group Report | Mon 06:00 | Management | Prior week PBGs — FF received, bubble yield, rosin yield, costs, cost/gram |
| 7 | Weekly 3-Way Reconciliation | Mon 06:00 | Compliance | METRC vs ERPNext vs physical, both warehouses, all variances |
| 8 | Open Work Orders Reminder | Daily 08:00 | Ops Team | WOs > 3 days old and not Completed — PBG, strain, days open, last activity |

**Email sending:** Use `frappe.sendmail()` with HTML table body. Recipient lists configured in `MTM Settings` custom DocType (or `site_config.json` keys).

---

## Phase 14 — Roles & Permissions

Create roles via fixtures (`Role` DocType).

| Role | Create/Edit | Verify/Approve | Transfer/Close |
|------|-------------|---------------|----------------|
| Lab Tech | Wash Batch, Press Batch, Job Card (own only) | ❌ (cannot verify own) | ❌ |
| Lab Supervisor | All lab DocTypes, WOs, Job Cards | Inventory Verification (if not the presser/washer) | Lab → Distro transfers, close WOs |
| Production Manager | All manufacturing DocTypes, BOMs, WOs | Full approval authority | Full transfer authority, BOM create/edit |
| Distro Manager | Stock Entry, Distro warehouse records | Distro receiving | Full distro transfer |
| Accounting | Purchase/Sales Invoice, Stock Ledger (read) | N/A | Read-only manufacturing |
| Compliance Officer | Read-only all DocTypes | View verifications and batches | Read-only |
| System Admin | All | All | All |

**Enforce in controllers:**
- `Inventory Verification`: `verified_by` field must not be any employee linked to the source Wash/Press Batch's tech fields.
- `Batch Sequence Lock`: Only Lab Supervisor or Production Manager can override a locked sequence.

---

## Phase 15 — Inter-Company Flow

### Entity Setup

- **TSBC Farms** → configured as a Company in ERPNext (or Supplier if single-entity)
- **Masters Touch Manufacturing** → separate Company
- **La Canna Distro** → separate Company (or Warehouse)

### Inter-Company PO → SO

1. Enable **Inter-Company** in ERPNext (Accounts → Settings → Enable Inter Company Invoices)
2. Link TSBC Farms Company ↔ MTM Company as inter-company pair
3. When MTM creates a PO to TSBC Farms → TSBC gets an auto-created Sales Order
4. When MTM submits a Purchase Receipt → TSBC gets a Delivery Note
5. When MTM submits a Purchase Invoice → TSBC gets a Sales Invoice (settlement of toll or raw material charge)

### Toll Fee Settlement

- MTM invoices toll customers using a Sales Invoice with `toll_fee_g × grams_produced` as the line item
- For internal TSBC ↔ MTM: inter-company invoices zero out at group level; only real cost is FF price set on TSBC's Sales Order

---

## Phase 16 — Fixtures & Migration

### Export Order (run after each build phase)

```bash
# From bench root
bench --site erp.alltechvirtual.com export-fixtures --app cannabis_management
```

Fixtures export the following (already configured in `hooks.py`):
- `Custom Field`
- `Client Script`
- `Server Script`
- `Property Setter`
- `Workflow`, `Workflow State`, `Workflow Action`

**Add to fixtures list in `hooks.py`:**
```python
fixtures = [
    # ... existing ...
    {"dt": "DocType", "filters": [["module", "=", "Master Touch Manufacturing"]]},
    {"dt": "Role", "filters": [["name", "in", ["Lab Tech", "Lab Supervisor", "Production Manager", "Distro Manager"]]]},
    {"dt": "Workstation", "filters": [["name", "like", "WS-%"]]},
    {"dt": "Operation", "filters": [["workstation", "like", "WS-%"]]},
    {"dt": "Workspace", "filters": [["module", "=", "Master Touch Manufacturing"]]},
]
```

### Migration Command

```bash
bench --site erp.alltechvirtual.com migrate
```

Run after each phase. Creates DocType tables, applies custom fields, loads fixtures.

### Patch Entry

After initial build, add a patch to `patches.txt` so the setup only runs once on fresh installs:

```
cannabis_management.patches.setup_master_touch_manufacturing
```

---

## Build Sequence (Recommended Order)

```
Phase 1  → Scaffold (30 min)
Phase 6  → Workstations (WS01–WS08), Routings, Operations in UI (2 hrs)
           ↳ Use $10/hr placeholder — update when Usman/Huzaifa finalize real costs
Phase 11 → Chart of Accounts structure + HR employee workstation fields (1 hr)
Phase 3  → Custom DocTypes:
           ↳ Production Batch Group first (parent to everything)
           ↳ Wash Batch + Wash Detail
           ↳ Press Batch + Press Detail
           ↳ Inventory Verification + METRC Package Verification
           ↳ METRC Retag Log
           (2–3 days total)
Phase 4  → Custom Fields via fixtures (append to custom_field.json) (3–4 hrs)
Phase 2  → Item Master: create 11 consumable items (cons-ice-water, cons-solvent, cons-bags-*, cons-parchment, cons-metrc-tag) — follow existing FF/Rosin/Primes naming for new strains (1 hr)
Phase 5  → BOMs in UI (clone BOM 1 → BOM 2, BOM 3, BOM 4) (2 hrs)
           ↳ Set yield threshold rule on Work Order controller
Phase 16 → bench migrate — verify all DocTypes create tables cleanly (30 min)
Phase 7  → Hooks + override scripts (1–2 days)
           ↳ Work Order, Job Card, Purchase Receipt, Wash/Press Batch, Stock Entry, Inv. Verification
Phase 8  → Batch auto-creation logic (1 day)
Phase 9  → Manufacture Stock Entry costing + yield threshold block (1 day)
Phase 10 → Quality Inspection templates + grade assignment logic (1 day)
Phase 14 → Roles + permissions (2 hrs)
Phase 15 → Inter-company config in UI (2 hrs)
Phase 12 → Slack alerts — all 11 (1 day)
Phase 13 → Email scheduled jobs (1 day)
Phase 16 → Final fixture export + full migrate + smoke test: WO → Job Card → SE:Manufacture
```

**Total estimated build:** 12–16 working days for a single developer familiar with the Frappe framework.

---

## Key File Locations (After Build)

```
cannabis_management/
├── master_touch_manufacturing/
│   ├── doctype/
│   │   ├── production_batch_group/
│   │   ├── wash_batch/
│   │   ├── wash_detail/
│   │   ├── press_batch/
│   │   ├── press_detail/
│   │   ├── inventory_verification/
│   │   ├── metrc_package_verification/
│   │   └── metrc_retag_log/
│   ├── overrides/
│   │   ├── work_order.py
│   │   ├── job_card.py
│   │   ├── purchase_receipt.py
│   │   ├── stock_entry.py
│   │   ├── wash_batch.py
│   │   ├── press_batch.py
│   │   └── inventory_verification.py
│   ├── utils/
│   │   └── slack.py
│   ├── tasks.py              ← all scheduled email jobs
│   └── workspace/
│       └── masters_touch_manufacturing/
├── fixtures/
│   └── custom_field.json     ← append Phase 4 fields here
└── hooks.py                  ← add doc_events + scheduler_events
```

---

---

## Additional Requirements Flagged (Pending Clarification)

### Lab Re-Tag / Barcode System

> **Flagged in session by Usman — needs client confirmation before build.**

When Fresh Frozen arrives from TSBC Farms, each package must be re-tagged with a new MTM METRC tag. The current plan handles this via the `METRC Retag Log` child table on Purchase Receipt (manual entry).

The additional requirement is a **barcode scanning workflow**:
- Lab tech scans the incoming TSBC METRC barcode
- System auto-populates `original_tag` in the Retag Log row
- Tech scans or generates a new MTM METRC tag barcode
- System populates `new_tag` and links to the ERPNext Batch record

**Implementation options:**
1. **ERPNext Barcode field** on the Batch DocType (native) — scan to fill METRC tag field. Requires barcode scanner peripheral at lab.
2. **Custom barcode JS** — client-side script on Purchase Receipt that opens a camera/scanner modal and pushes values into the child table row.
3. **Mobile app / PWA** — if techs use phones, a lightweight PWA scan page that creates the Retag Log entry and syncs to ERPNext.

**Action:** Usman to clarify with client which scanning hardware/devices are available in the lab. Decision needed before this feature is built.

---

## Open Action Items

| # | Task | Owner | Phase | Status |
|---|------|-------|-------|--------|
| 1 | Finalize electricity, rent & consumable costs per workstation (WS01–WS08) | Usman / Huzaifa | Phase 6 | ⏳ Pending |
| 2 | Complete Routing setup for all operations (currently only Wash is done) | Huzaifa | Phase 6 | ⏳ In Progress |
| 3 | Define item variants + attribute values (Prime, Distillate, Food Grade, Trim) — confirm with client | Huzaifa | Phase 2 | ⏳ Pending |
| 4 | Set and confirm yield threshold values — 2.5% for bubble hash agreed; rosin threshold TBD | Team | Phase 5 | ⏳ Pending |
| 5 | Test full manufacturing flow end-to-end: Work Order → Job Card → Stock Entry: Manufacture | Huzaifa | Phase 7/9 | ⏳ Pending |
| 6 | Clarify lab re-tag / barcode scanning requirement with client (hardware, device type) | Usman | Additional | ⏳ Pending |
| 7 | Link employee/wage setup to workstations in HR module — set `default_workstation` + `hourly_wage_rate` on all lab employees | Huzaifa | Phase 11 | ⏳ Pending |
| 8 | Confirm WIP account structure with accountant — item-group-wise mapping approved? | Usman | Phase 11 | ⏳ Pending |
| 9 | Build Routing 2 (Bubble Hash Press) and verify it generates correct Job Cards | Huzaifa | Phase 6 | ⏳ Pending |

---

*Masters Touch Manufacturing × La Canna Distro — Internal Build Plan — Confidential*
