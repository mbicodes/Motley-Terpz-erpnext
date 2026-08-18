# TSBC Ranch — Farm / Cultivation Module: Testing Guide

A step-by-step dry-run of the full cultivation lifecycle, using pre-created demo
entries on **stage.alltechvirtual.com** (`https://erp.motleyterpz.io/app`).

Everything below can be clicked through in the UI. Nothing here writes to METRC.

---

## 0. Demo data already created for you

| Type | Name | State |
|---|---|---|
| Item (strain) | **S-0014** — "Farm Demo Strain (Blue Dream)" | stock item, batch-tracked |
| Batch | **FARM-DEMO-IMMATURE** | 20 immature plants, nothing promoted yet |
| Batch | **FARM-DEMO-FLOWER** | 6 plants already promoted → **Flowering** |
| Farm Production Batch | **FPB-2026-0001** | empty harvest, for the rollup test |
| Warehouse | **METRC Sandbox - MTM** | use as Output / Dry Room |

The 6 Flowering demo tags on FARM-DEMO-FLOWER:

```
1A4FF0300000259000020001
1A4FF0300000259000020002
1A4FF0300000259000020003
1A4FF0300000259000020004
1A4FF0300000259000000005
1A4FF0300000259000020005
```

> Tip: open the **Metric Tag** list and filter `Source Batch = FARM-DEMO-FLOWER`
> to see them, or `Growth Stage = Flowering`.

---

## Test 1 — Change Growth Phase (Batch → tagged plants)

*Replaces manual Starting/Ending tag entry — pulls unused tags from the pool.*

1. Open **Batch → FARM-DEMO-IMMATURE**.
2. Confirm **Immature Plant Count = 20** (Farm / Cultivation section).
3. Click **Farm ▾ → Change Growth Phase**.
4. Enter **Number of Plants = 5**, **Output Warehouse = METRC Sandbox - MTM**, click **Promote**.

**Expect:**
- ✅ "5 plants promoted. 15 immature remaining."
- Batch now shows **Immature = 15**, **Tagged Count = 5**.
- Open the **Metric Tag** list → filter `Source Batch = FARM-DEMO-IMMATURE`: 5 tags,
  each **Growth Stage = Vegetative**, **Status = Active**, Warehouse set, Item = S-0014.

### Error path — not enough tags
Repeat step 3 but request **99999** plants → ✅ blocked:
*"Cannot promote 99999 plants — only 15 remain immature in this batch."*
(If you ever exhaust the ~9,600-tag pool, you'd instead see *"Only N unused tags
available…"* — that's the pool-exhaustion guard.)

---

## Test 2 — Plant Cost Entry (nutrients/fertilizer cost accumulation)

*Splits a cost evenly across the plants it was applied to.*

1. New **Plant Cost Entry**.
2. **Product** = S-0014 (or any nutrient item), **Total Cost = 300**.
3. Under **Tags Covered**, add the 6 FARM-DEMO-FLOWER tags above.
4. **Save**, then **Submit**.

**Expect:**
- ✅ 300 ÷ 6 = **50** added to each tag's **Accumulated Cost**.
- Open any of those Metric Tags → **Accumulated Cost = 50**.
- (Cancelling the entry reverses it — each tag drops back by 50.)

---

## Test 3 — Teardown: Regular (harvest + cost transfer + Repack)

1. New **Teardown**.
2. **Type = Regular**, **Weight Unit = g**, **Dry Room = METRC Sandbox - MTM**,
   **Output Item = S-0014**, **Linked Harvest = FPB-2026-0001**.
3. Under **Teardown Tags**, add **3** of the Flowering demo tags. The **Strain**
   column auto-fills.
4. Enter weights, e.g. 10 / 20 / 30. (Or use **Weights ▾ → Total Weights** to
   split one combined weight evenly by strain; **Scan Tag → Weight** focuses a
   row by scanning.)
5. **Save → Submit**.

**Expect:**
- ✅ Each of the 3 tags → **Growth Stage = Harvested**, **Accumulated Cost = 0**.
- Teardown **Total Cost Transferred = 150** (3 × 50), **Status = Completed**.
- A **draft Repack Stock Entry** is created into the Dry Room (a link is shown in
  the message) — 60 g of S-0014 received. It's left in draft for the operator to
  add consumed inputs.
- Open **FPB-2026-0001** → **Costs to Date** now includes the 150 transferred.

### Error path — non-Flowering tag rejected
Start a new Teardown and add a tag that is **Vegetative** (one of the Test 1
tags) → ✅ on Submit: *"Row 1: Metric Tag … is 'Vegetative', not Flowering — it
cannot be torn down."*

---

## Test 4 — Teardown: Manicure (partial cost, plant stays alive)

1. New **Teardown**, **Type = Manicure**, Dry Room + Output Item as above.
2. Add **1** of the remaining Flowering demo tags (one you did *not* harvest in
   Test 3). It has Accumulated Cost 50 from Test 2.
3. Set **Cost % Transferred = 40**, **Weight = 15**.
4. **Save → Submit**.

**Expect:**
- ✅ **20** transferred (40% of 50), tag **Accumulated Cost = 30** (60% remains).
- Tag **stays Flowering** (plant is alive) — *not* Harvested.
- A second Manicure can only draw from the remaining 30 (no double-spend).

---

## Test 5 — Destroy & Record Waste (bulk, from the Metric Tag list)

1. Open the **Metric Tag** list, filter `Source Batch = FARM-DEMO-IMMATURE`.
2. Tick 2 of the **Vegetative** tags from Test 1.
3. **Actions ▾ → Destroy Plants**. Fill Disposal Method (e.g. "Compost"),
   Reason = "Disease", Logged By = an Employee, optional weight. Click **Destroy**.

**Expect (destructive):**
- ✅ Both tags → **Growth Stage = Destroyed**, **Destroyed By** stamped.
- A **Plant Waste Log** is created per tag (open the list to see them).
- FARM-DEMO-IMMATURE **Destroyed Count** increments.

4. Now tick a different Vegetative tag → **Actions ▾ → Record Waste (non-destructive)**.

**Expect (non-destructive):**
- ✅ A **Plant Waste Log** is created, but the tag's **Growth Stage is unchanged**
  (plant stays alive) and **Destroyed By is NOT set**. This is the key difference.

---

## Test 6 — 48-hour plant-count lock (compliance)

- **FARM-DEMO-IMMATURE** was just created, so editing **Immature Plant Count**
  directly on the form still **works** (within the 48h window).
- The lock only triggers after 48h. To prove the rule without waiting, ask me to
  age the batch; you'll then get: *"Immature Plant Count can only be adjusted
  within 48 hours of batch creation…"*. Note that **Change Growth Phase** and
  **Destroy** still adjust counts after 48h — only *manual* edits are blocked.

---

## Test 7 — Individual KPI: Plant Loss Rate

After Test 5, the destroyed tags are attributed to the **Logged By** employee.
Plant Loss Rate = destroyed ÷ total tagged plants for that employee's batches.
It's available as a server function (`cannabis_management.farm.get_plant_loss_rate`)
— tell me where you want it surfaced (a report, a Number Card, or the Farm
Employee KPI Profile) and I'll wire it in.

---

## Gap-check (from the spec, Section 13) — all covered

| Scenario | Behaviour |
|---|---|
| Fewer tags than requested | Explicit error, no silent under-promote (Test 1) |
| Non-Flowering tag in a Teardown | Rejected on submit (Test 3 error path) |
| Accumulated cost after a Regular teardown | Reset to 0 — no double-count (Test 3) |
| Manicure double-spend | Cost decremented immediately; 2nd draw only from remainder (Test 4) |
| Existing non-Farm Metric Tag / Batch use | Untouched — all new fields optional/nullable |
| Who destroyed a plant | `Destroyed By` stamped at destroy time (Test 5) |
| Plant-count edit after 48h | Blocked in Batch validate (Test 6) |

---

## Resetting the demo data

To wipe the demo entries and return the pool tags to **Unused**, ask me to run
the reset, or:

- Cancel/delete any Teardown & Plant Cost Entry you created.
- Delete the demo Plant Waste Logs.
- Set the demo Metric Tags back to `Status = Unused`, clear the Farm fields.
- Delete `FARM-DEMO-IMMATURE`, `FARM-DEMO-FLOWER`, `FPB-2026-0001`, item `S-0014`.

I can do this in one command whenever you're done testing.
