# Cultivation Workflow — Cannabis Management

> End-to-end grow → harvest → finishing process as implemented in the
> **`cannabis_management`** app (module: *Cannabis Management*).
> The separate `agriculture` app (stock Frappe Crop / Crop Cycle) is **not** used by
> this process. Strains are modeled as plain **Items**, not Crops.

---

## 1. Overview

The cultivation lifecycle is modeled as a chain of **submittable documents**, each linked
back to a central harvest object (**Farm Production Batch**) via a `linked_harvest` field.
There is **no Frappe `Workflow` document** — stage progression is enforced by `Select`
fields (`stage`, `task_type`) plus controller `on_submit` logic. Harvest output reaches
inventory through **Stock Entries** (Material Receipt / Repack), **not** Work Orders/BOMs.

```
 PROPAGATION        GROW (veg→flower)      HARVEST LABOR         HARVEST HUB           FINISHING
┌────────────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────┐     ┌───────────────┐
│  Cloning   │────▶│ Plant Batch  │────▶│  Farm Labor  │────▶│ Farm Production│────▶│  Conversion   │
│   Batch    │     │              │     │   Session    │     │     Batch      │     │    Entry      │
│ CB-YYYY-#### │   │ PB-YYYY-####  │    │ FLS-YYYY-#### │     │  FPB-YYYY-####  │    │  (repack)     │
└─────┬──────┘     └──────┬───────┘     └──────┬───────┘     └───────┬────────┘     └──────┬────────┘
      │ on submit         │ stage:            │ Bucking =            │ cost/revenue         │ RM → FG
      ▼                   │ Immature→Veg→     │ harvest processing   │ ROLLUP (P&L)         ▼
 Material Receipt         │ Flower→Harvested  ▼                      ▲  ▲  ▲            Repack Stock
 Stock Entry              │                Repack Stock Entry       └──┴──┴─ recalculated Entry (draft)
 (clones in)             ...               (buck outputs, draft)     on every linked submit
```

---

## 2. Stage-by-stage

### Stage 1 — Propagation: `Cloning Batch`
`cannabis_management/cannabis_management/doctype/cloning_batch/`

- Clones cut from a mother plant (`mom_plant_reference`); METRC tag (`metrc_tag`) assigned.
- Clone rows in `clone_details`; labor captured via `labour_hours` × `labour_rate`.
- KPIs: `clones_rooted`, `total_clones_taken`, `rooting_success_rate`, `clones_per_hour`.
- **Naming:** `CB-.YYYY.-.####`
- **`validate`:** `calculate_totals()` (clone qty, labor cost, cost-per-clone) +
  `validate_warehouse_company()` (target warehouse must belong to `company`).
- **`on_submit`:** `create_stock_entry()` → creates **and submits** a **Material Receipt**
  Stock Entry (clones into `target_warehouse`), booking labor as an additional cost to the
  `Harvest Labor - TSBC` account → then `update_linked_harvest(self)`.

### Stage 2 — Grow: `Plant Batch`
`cannabis_management/cannabis_management/doctype/plant_batch/`

- The real **stage machine**: `stage` = **Immature → Vegetative → Flower → Harvested**.
- Links to propagation via `source_cloning_batch`; strain via `strain` (Link → Item).
- Tracks `plant_count`, `wet_weight`, `dry_weight`, plus child tables `loss_log`
  (Plant Batch Loss Log) and `input_log` (Plant Batch Input Log).
- **Naming:** `PB-.YYYY.-.####`
- **`validate`:** `calculate_totals()` → derives `plants_lost`, `plants_harvested`,
  `total_input_cost`, and analytics `moisture_loss_pct`, `waste_pct`, `days_to_flower`,
  `yield_per_plant`.
- **`on_submit`:** `update_linked_harvest(self)`.

### Stage 3 — Harvest labor: `Farm Labor Session`
`cannabis_management/cannabis_management/doctype/farm_labor_session/`

- `task_type` = **Planting / Deleaf / Bucking**.
- **Bucking is the harvest-processing (assembly) step** — wet harvested material is turned
  into dried/packaged outputs via child tables `ingredients` (consumed), `outputs`
  (produced), `additional_costs`.
- Computes `yield_pct`, `moisture_loss_pct`, assembly cost (`total_assembly_cost`).
- **Naming:** `FLS-.YYYY.-.####`
- **`validate`:** `calculate_totals()`; for Bucking, `calculate_bucking_assembly_totals()`
  + `validate_warehouse_company()`.
- **`on_submit` (Bucking):** `create_bucking_stock_entry()` → creates a **Repack** Stock
  Entry (ingredients → outputs); additional costs mapped to `Farm {cost_type} - {abbr}`
  expense accounts (fallback: company Stock Adjustment account). **Left in Draft** on
  purpose — the source plant is METRC-tracked, not an ERPNext stock item. Then
  `update_linked_harvest(self)`.

### Stage 4 — Harvest hub / P&L: `Farm Production Batch`
`cannabis_management/cannabis_management/doctype/farm_production_batch/`

- **Not submittable, not an inventory object** — the central harvest record everything links
  to. `route` = **Fresh Frozen / Flower / Biomass** sets the downstream path.
- **Naming:** `FPB-.YYYY.-.####` (title = `harvest_name`).
- Rolled-up financials: `propagation_cost`, `labor_cost`, `costs_to_date`,
  `revenue_to_date`, `gross_profit`, `net_to_date`.
- **`recalculate_rollups()`** (raw SQL) sums:
  - propagation labor from submitted **Cloning Batches**,
  - bucking assembly + labor from submitted **Farm Labor Sessions**,
  - `total_input_cost` from submitted **Plant Batches**,
  - revenue from **Sales Invoices** (via `custom_linked_harvest`).
- Module-level **`update_linked_harvest(doc, method=None)`** is the shared `on_submit`
  hook reused by Cloning Batch, Plant Batch, Farm Labor Session, and Sales Invoice — it
  reads `linked_harvest` / `custom_linked_harvest` and re-runs `recalculate_rollups()`.

### Stage 5 — Finishing: `Conversion Entry`
`cannabis_management/cannabis_management/doctype/conversion_entry/`

- The custom **repack/conversion** flow: multi-input → multi-output via `conversion_type`
  (`1 to 2`, `2 to 1`, `3 to 1` … `7 to 1`, `2 to 2`), raw materials (`raw_material_1..7`)
  → finished goods (`finished_good_1..2`), with a **job timer** (`time_logs`).
- **`validate`:** validates RM/FG rows per `conversion_type`; enforces that vape/rosin/
  packaged finished goods include a `Hardware Inventory` raw material; sums timer minutes.
- **`before_submit`:** blocks if the job timer is still "Work In Progress".
- **`on_submit`:** `_create_repack_stock_entry()` → one **Repack** Stock Entry per row,
  source valuation (from `Bin.valuation_rate`) distributed to finished goods by qty ratio,
  plus workstation/operating cost — inserted as **draft**.
- Whitelisted APIs: **`make_conversion_entry(source_name)`** (draft CE from a Sales Order,
  pre-filling shortage rows for company *Master Touch Manufacturing* into warehouse
  `Conversion - MTM`) and **`make_ce_time_log(args)`** (timer start/pause/resume/complete).
- `hooks.py` doc_event: `Conversion Entry.on_submit` → Slack notification.

---

## 3. Harvest → inventory (three Stock Entry paths)

| Source | Stock Entry type | State | What it does |
|---|---|---|---|
| Cloning Batch | **Material Receipt** | Submitted | Receives clones into `target_warehouse`; labor as additional cost |
| Farm Labor Session (Bucking) | **Repack** | Draft | Consumes `ingredients`, produces `outputs`; costs → farm expense accounts |
| Conversion Entry | **Repack** | Draft | Raw materials → finished goods; valuation distributed by qty ratio + workstation cost |

There is **no Work Order / BOM** for cultivation — this is deliberate.

---

## 4. Supporting pieces

- **`Farm Daily Log`** — daily scouting/compliance: `scouting_completed`, `issue_reported`,
  `dcc_ready_status` (Pass/Fail), `metrc_open_corrections`. Naming `format:{logged_by}-{log_date}`.
- **METRC compliance layer** — `metric_tag` doctype + Stock Entry validate/submit hooks
  track regulatory tags across every stock move.
- **Hub UI**
  - Workspace **"Harvesting Process"** → Farm Daily Log, Cloning Batch, Farm Labor Session,
    Farm Production Batch + **CEO Farm Dashboard** / **OPS Farm Dashboard** pages.
  - Workspace **"Conversion"** → Conversion Entry.
- **Reports** most relevant here: `manufacturing_traceability_report`,
  `stock_valuation_lineage`, `gross_profit_stock_items`, `metrc_variance`.

---

## 5. Key notes / caveats

1. **No Frappe `Workflow` document.** The "workflow" is Select fields (`stage`, `task_type`)
   + controller `on_submit` logic — there are no role-gated approval transitions.
2. **Bucking & Conversion Repack entries are left in Draft** intentionally (METRC-tracked
   source material is not an ERPNext stock item); they are reviewed/submitted manually.
3. **`Production Batch`** doctype exists but its controller is a no-op (`pass`) — legacy.
4. The **`teardown`** / `teardown_tag` doctype folders contain only stale `__pycache__`
   (no source) — orphaned, not part of the live model.
5. The **`agriculture`** app is unused by this workflow.

---

## 6. Doctype quick reference

| Doctype | Role | Submittable | Naming |
|---|---|---|---|
| Cloning Batch | Propagation | Yes | `CB-.YYYY.-.####` |
| Plant Batch | Grow (stage machine) | Yes | `PB-.YYYY.-.####` |
| Farm Labor Session | Harvest labor / Bucking | Yes | `FLS-.YYYY.-.####` |
| Farm Production Batch | Harvest hub / cost-revenue rollup | No | `FPB-.YYYY.-.####` |
| Conversion Entry | Finishing / repack | Yes | (system) |
| Farm Daily Log | Daily compliance log | — | `format:{logged_by}-{log_date}` |
