# METRC Integration — Functional Guide

**For:** Functional Consultants and Project Managers
**System:** ERPNext v15 · `cannabis_management` app · site `stage.alltechvirtual.com`
**Regulator:** California Metrc (Franwell) Web API v2
**Document date:** 4 August 2026
**Status:** Built and installed on staging · pull-only · not yet in production

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [What Metrc is and why this matters](#2-what-metrc-is-and-why-this-matters)
3. [Scope — what is in and what is not](#3-scope--what-is-in-and-what-is-not)
4. [How the two systems map to each other](#4-how-the-two-systems-map-to-each-other)
5. [What users actually see](#5-what-users-actually-see)
6. [Business processes, step by step](#6-business-processes-step-by-step)
7. [What runs automatically, and when](#7-what-runs-automatically-and-when)
8. [Exception handling — the daily routine](#8-exception-handling--the-daily-routine)
9. [Variance management](#9-variance-management)
10. [Configuration guide](#10-configuration-guide)
11. [Roles and permissions](#11-roles-and-permissions)
12. [Testing and UAT](#12-testing-and-uat)
13. [Project status and RAID log](#13-project-status-and-raid-log)
14. [Go-live plan](#14-go-live-plan)
15. [Decisions needed from the business](#15-decisions-needed-from-the-business)
16. [Glossary](#16-glossary)
17. [Appendix A — Field reference](#appendix-a--field-reference)
18. [Appendix B — Status reference](#appendix-b--status-reference)

---

## 1. Executive summary

### What has been built

A two-way integration between ERPNext and California Metrc, the state's mandatory
seed-to-sale tracking system. It reports sales, transfers, stock adjustments and
manufacturing activity to the state, pulls the state's view of inventory back into
ERPNext, and flags every place the two disagree.

### Where it stands today

| Area | Status |
|---|---|
| Connection to Metrc **sandbox** | Working — 20 test facilities reachable |
| Pulling data from Metrc | Working — 413 packages, 9,709 tags imported |
| Writing data to Metrc | Built and tested, **switched off** by design |
| Connection to Metrc **production** | **Blocked** — awaiting Metrc approval |
| Automated scheduling | **Paused** on this server — runs manually only |
| End-to-end functional test | **Passed, 11 of 11 checks** |

### The one-line summary for a steering committee

*The integration is functionally complete and proven against Metrc's test
environment. Two external dependencies — Metrc's production approval and a
server timezone correction — stand between us and go-live. Neither is a
development task.*

### Two things that need a decision before go-live

1. **The server's timezone is set to Alaska, not California.** Metrc interprets
   sale times as facility-local. Until this is corrected, evening sales would be
   reported on the wrong calendar day. See §13, Risk R1.
2. **Metrc production access has not been granted.** This is an application and
   review process with Metrc, not a configuration change. See §13, Risk R2.

---

## 2. What Metrc is and why this matters

Metrc is the track-and-trace system California requires every licensed cannabis
business to use. Every plant, package and sale must be recorded there. The state
audits against Metrc, not against our ERP.

**The compliance consequence:** if ERPNext says we hold 500g and Metrc says 480g,
the state believes Metrc. An unexplained discrepancy is a finding. Repeated or
large discrepancies risk licence action.

**What that means for the design.** The integration treats Metrc as the system of
record for compliance state. Where the two disagree we **report the difference and
stop** — we never silently overwrite either side. A quantity difference is either a
data-entry error or a genuine physical discrepancy, and both need a human to look
at them. Automatically "correcting" one system to match the other would destroy the
evidence of what actually happened.

**Every physical unit carries a Metrc tag** — a printed label with a unique
number, ordered from the state. Tags are the primary key of the whole system. They
cannot be invented; they are purchased, received, and consumed.

---

## 3. Scope — what is in and what is not

### In scope and built

| Capability | Direction | Notes |
|---|---|---|
| Package (inventory) sync | Metrc → ERPNext | Every 30 min when scheduled |
| Tag pool sync | Metrc → ERPNext | Unused tags available for assignment |
| Item and strain sync | Metrc → ERPNext | Matches, does not create Items |
| Transfer / manifest sync | Metrc → ERPNext | Incoming and outgoing |
| Lab result sync | Metrc → ERPNext | Pass/fail onto the Batch |
| Sales receipts | ERPNext → Metrc | From Sales Invoice |
| Outgoing transfer templates | ERPNext → Metrc | From Delivery Note |
| Stock adjustments | ERPNext → Metrc | From Stock Reconciliation and Stock Entry |
| Processing jobs | ERPNext → Metrc | From Work Order and Manufacture Stock Entry |
| Variance reporting | Internal | Daily email plus on-demand report |
| Full audit log | Internal | Every request and response retained |

### Explicitly out of scope

| Not included | Why |
|---|---|
| Creating Items automatically from Metrc | An Item without an item group, UOM or valuation breaks every downstream transaction. Item creation stays a controlled master-data activity. |
| Cultivation day-to-day (plant moves, feeding logs) | The API supports it; the business has not asked for it. The plant endpoints are mapped in the technical guide if this is added later. |
| Patient and caregiver sales | Requires collecting patient licence numbers we do not hold today. Retail sales default to "Consumer". |
| Creating outgoing transfers directly | **A Metrc API limitation, not a design choice.** Metrc has no "create outgoing transfer" endpoint. We create a fully-populated *template* that dispatch promotes to a live manifest in the Metrc portal. |
| Metrc webhooks (push notifications) | Availability depends on our Metrc service tier. Design assumes polling; webhooks would be an optimisation. |

---

## 4. How the two systems map to each other

This is the most important section for a functional consultant. **The mapping was
largely pre-existing** — this project built on structures already in the app rather
than inventing new ones.

| Metrc concept | ERPNext record | Linked by |
|---|---|---|
| Facility / Licence | **Warehouse** | METRC License # on the Warehouse |
| Package | **Batch** | METRC Tag on the Batch |
| Physical tag label | **Metric Tag** | The tag code itself |
| Item (product) | **Item** | METRC Item Name |
| Strain | **Strain** | Name |
| Sales receipt | **Sales Invoice** | METRC Receipt ID |
| Transfer / manifest | **Delivery Note** (out), **Purchase Receipt** (in) | METRC Transfer ID |
| Processing job | **Work Order** / Manufacture Stock Entry | METRC Job ID |
| Package adjustment | **Stock Reconciliation** / Stock Entry | Logged in the outbox |

### The three rules that follow from this

**A Warehouse is a licence.** Every Metrc-relevant Warehouse must carry a METRC
License #. This is how the system decides which facility a transaction belongs to
and which credentials to use. A Warehouse without one is invisible to Metrc — and
that is a legitimate configuration for non-cannabis stores.

**A Batch is a package.** One Batch equals one physical tagged package. This is
already how the business works; the integration formalises it.

**Quantity is never converted.** If Metrc holds a package in grams, we report
grams. Converting between grams and ounces introduces rounding drift, and drift
against a state system reads as a discrepancy.

### A critical operational detail

Tags reach the stock ledger through an ERPNext feature called an **Inventory
Dimension**, configured in this app as *Muid*. On stock documents this appears as a
**Muid** field on each item row.

> **Filling in the Batch alone is not sufficient.** The Muid field is what carries
> the tag into the stock ledger and keeps quantities per-tag. A row with a Batch but
> no Muid produces stock the compliance reporting cannot see. This was confirmed in
> testing: 2,495g of received stock showed as zero against its tag until Muid was
> populated.

This must be covered in end-user training and, ideally, enforced by validation.

---

## 5. What users actually see

The design principle: **nobody should have to open a technical screen to know
whether something is reported to the state.**

### On every document that reports to Metrc

Sales Invoice, Delivery Note, Stock Entry, Stock Reconciliation and Work Order all
gain the same three things after submission:

1. **A status badge in the document header** — green *Synced*, orange *Queued*, red
   *Failed* or *Parked*, grey *Not Tracked*.
2. **A red banner** across the top when something failed, showing the reason in
   plain language. A silent compliance gap is the failure mode that matters most,
   so failures are made loud.
3. **A "METRC" button menu** with three actions: **Resync** (retry now), **View
   METRC Log** (the exact conversation with the state system), and **View Outbox**
   (the queued instruction).

There is also a collapsible **METRC** section holding the Receipt or Transfer ID,
the licence used, and when it last synced.

### On the Batch

The Batch screen shows Metrc's view side by side with ours:

- **METRC Quantity** — what the state believes we hold
- **METRC Variance** — the difference against our stock ledger
- **METRC Package Status** — Active, On Hold, In Transit, Finished
- **METRC Lab Result** — Passed, Failed or Not Tested

A non-zero variance raises a red banner reading *"ERPNext holds X but METRC holds
Y. Investigate before selling."* A failed lab result shows a red **Lab: FAILED**
badge. **Product with a failed lab result must not be sold**, and this is the
control that makes that visible at the point of use.

### On the Item

A **METRC Tracked** checkbox, the **METRC Item Name** that must match the state
system exactly, and the Metrc-assigned ID once confirmed.

> Only items with **METRC Tracked** ticked are ever reported. This is the master
> switch for what the state sees, and it is the first thing to check when something
> unexpectedly does not sync.

### The METRC workspace

A dedicated sidebar section grouped into three cards:

| Card | Contents | Who uses it |
|---|---|---|
| **Configuration** | Metrc Settings | Administrator |
| **Monitoring** | Sync State, Outbox, API Log, Variance report | Compliance |
| **Inventory** | Metric Tag, Batch, Item | Stock team |

**Metrc Settings** also carries a live dashboard: environment, queued and parked
counts, variance totals, and a per-endpoint sync table.

---

## 6. Business processes, step by step

### 6.1 Selling product

```
  Sales Invoice submitted
          |
          v
  Is the item METRC Tracked?  -- no -->  status "Not Tracked", nothing sent
          |  yes
          v
  Does the row have a tagged Batch?  -- no -->  submission BLOCKED with a message
          |  yes
          v
  Instruction queued   -> status "Queued"
          |
          v
  Background worker sends it to Metrc
          |
          +-- success --> status "Synced", Receipt ID recorded
          |
          +-- rejected --> status "Parked", red banner, needs a human
          |
          +-- Metrc down --> retried automatically, up to 6 times
```

**Why the invoice is never blocked by Metrc being unavailable.** The instruction is
written to a queue in the same database transaction as the invoice. The invoice
succeeds or fails on its own merits; the reporting happens moments later in the
background. A Metrc outage cannot stop the business from invoicing.

**If the invoice is cancelled**, a deletion instruction is queued automatically, so
a cancelled sale does not stay reported to the state.

### 6.2 Sending product to another licensee

Submitting a **Delivery Note** creates a fully-populated **transfer template** in
Metrc containing the recipient licence, the package tags, the vehicle and driver
details, and the planned route.

> **Dispatch must then open the Metrc portal and promote that template to a live
> manifest.** This is not an oversight — Metrc's API provides no way to create an
> outgoing transfer directly. The template removes the retyping and the transcription
> errors that come with it. Once the manifest exists, its number flows back onto the
> Delivery Note on the next sync.

The Customer must have a **License Number** recorded, or submission is blocked with
an explanatory message. Metrc will not accept a transfer without a recipient
licence.

### 6.3 Correcting stock

A **Stock Reconciliation** reports the *difference* to Metrc, not the new total.
Counting 480g where the system said 500g reports −20g.

The document carries a **METRC Adjustment Reason**, which must be one of Metrc's
official reasons — Damage, Scale Variance, Incorrect Quantity, and so on. The valid
list is pulled from Metrc automatically and refreshed hourly.

### 6.4 Manufacturing

| Event | What is reported |
|---|---|
| Work Order submitted | A processing job starts; input packages are consumed |
| Manufacture Stock Entry submitted | Output packages are created, waste recorded, job closed |

Output packages automatically claim tags from the unused pool. If the pool is
empty, submission is blocked with a clear message — the correct behaviour, since
inventing a tag number is not possible.

### 6.5 Receiving product

Incoming transfers are pulled from Metrc and matched to **Purchase Receipts** by
package tag. The manifest number is stamped onto the receipt automatically. No user
action is required.

---

## 7. What runs automatically, and when

| Job | Frequency | What it does |
|---|---|---|
| Master data | Hourly | Items, strains, facilities, tag pool, valid reason lists |
| Inventory | Every 30 minutes | Packages and transfers — the compliance-critical path |
| Outbox worker | Every 5 minutes | Sends queued instructions to Metrc |
| Operations | Daily, 02:00 | Sales receipts and lab results |
| Variance report | Daily, 06:00 | Emails discrepancies to the compliance contact |
| Log housekeeping | Weekly, Sunday | Trims audit logs past their retention period |

**Why 30 minutes and not real-time.** Metrc rate-limits per facility, and the state
does not require real-time reporting. Thirty minutes keeps discrepancies same-day —
far cheaper to resolve than week-old ones — without exhausting the rate limit.

> **Currently these do not run.** The scheduler is paused on this server, so every
> sync is triggered manually. Enabling it is a one-line change and a project
> decision, not a development task.

---

## 8. Exception handling — the daily routine

### The five statuses

| Status | Meaning | Action |
|---|---|---|
| **Not Tracked** | No Metrc-tracked items on this document | None — normal |
| **Queued** | Waiting to be sent | None — should clear within 5 minutes |
| **Synced** | Metrc accepted it | None |
| **Failed** | Temporary problem; retrying automatically | Watch. Clears itself unless it becomes Parked |
| **Parked** | Metrc rejected it, or retries exhausted | **A human must act** |

### Parked is the one that matters

A parked instruction will never retry on its own. It represents work the state has
not been told about. Common causes and their fixes:

| Cause | Fix |
|---|---|
| Package tag does not exist in Metrc | Correct the Batch's METRC Tag, then Resync |
| Adjustment reason not recognised | Set a valid METRC Adjustment Reason, then Resync |
| Unit of measure not mapped | Add the mapping in Metrc Settings, then Resync |
| Recipient licence missing or wrong | Correct the Customer's License Number, then Resync |
| Credentials rejected | Escalate — a configuration problem, not a data one |

### Suggested daily routine for the compliance owner

1. Open the **METRC** workspace and check the **Parked** count. Target: zero.
2. Work each parked item: open the source document, read the red banner, fix the
   cause, press **Resync**.
3. Read the overnight **variance report** email and investigate anything material.
4. Check **Sync State** — every cursor should read *Success*.

The system also emails the compliance contact automatically when a sync fails
repeatedly or when parked instructions accumulate, so this routine is a safety net
rather than the only line of defence.

---

## 9. Variance management

The variance report answers one question: **where do Metrc and our stock ledger
disagree?** It is valuable from day one, before any writing to Metrc is switched on.

### The four categories

| Category | Meaning | Severity |
|---|---|---|
| **Quantity variance** | Both systems know the package; quantities differ | Investigate |
| **Untagged stock** | We hold tracked product with no Metrc tag | **Highest** — unreported inventory |
| **Orphan tags** | Metrc shows an active package we have no record of | Usually an unmapped Item |
| **Unmapped items** | Marked tracked but Metrc has never confirmed them | Configuration gap |

**Untagged stock is the dangerous direction.** Product we physically hold but have
not reported is the finding a regulator cares most about.

### The correction process

1. Investigate — count the physical product.
2. Decide which system is wrong.
3. If ERPNext is wrong, raise a **Stock Reconciliation**, tick **METRC Correction
   Made**, and record the reason in Compliance Notes.
4. If Metrc is wrong, the same reconciliation pushes the correcting adjustment.
5. Confirm the variance clears on the next sync.

The correction is itself a document, which is exactly what an audit needs.

---

## 10. Configuration guide

All configuration is in **Metrc Settings** (METRC workspace → Configuration).

### Step 1 — Credentials

| Field | Value |
|---|---|
| Environment | Sandbox or Production |
| Integrator (Software) API Key | Company-wide key from Metrc Connect |

Press **Test Connection**. A successful test lists every facility the keys can
reach and shows which are mapped to a Warehouse.

### Step 2 — Facilities

One row per Metrc licence:

| Field | Purpose |
|---|---|
| License Number | The Metrc licence, e.g. `C12-1000001-LIC` |
| User API Key | The per-user key for that facility |
| Warehouse | The ERPNext Warehouse this licence represents |
| Facility Timezone | Drives sale times. California = `America/Los_Angeles` |
| Active | Whether this facility syncs |
| Sync scope | Which data types to sync for this licence |

**Set the sync scope per licence type.** A retailer has no plants; a cultivator has
no sales receipts. Polling endpoints a licence cannot use wastes the rate limit and
generates misleading errors.

**Import Facilities** populates this table from Metrc, avoiding typos in licence
numbers.

### Step 3 — UOM mapping

Metrc accepts exactly eleven units: Each, Grams, Kilograms, Milligrams, Ounces,
Pounds, Fluid Ounces, Gallons, Liters, Milliliters, Pints.

Every ERPNext UOM used on a tracked item must map to one of these. Eleven common
mappings are pre-populated. An unmapped unit blocks the push with a clear message
naming the unit.

### Step 4 — Operating mode

| Setting | Meaning |
|---|---|
| **Enabled** | Master switch. Off = nothing happens at all |
| **Enable Push** | Off = read-only. Data comes in, nothing goes out |
| **Dry Run** | Builds and logs the payload but does not transmit |

The safe sequence is **Enabled → verify pulls → Enable Push with Dry Run → inspect
payloads → turn Dry Run off**.

### Step 5 — Items

For each product reported to the state: tick **METRC Tracked** and set **METRC Item
Name** to match Metrc exactly.

> Nothing syncs until this is done. It is the single most common reason for "the
> integration isn't working".

---

## 11. Roles and permissions

| Role | Can see | Can do |
|---|---|---|
| **System Manager** | Everything | Configure, resync, retry parked items |
| **Stock Manager** | Logs, outbox, tags, variance | Resync documents, work exceptions |
| **Stock User** | Metrc fields on documents | Read only — sync fields are system-maintained |

Metrc fields on documents are **read-only by design**. They record what the state
was told; a user editing them would break the audit trail.

### Recommended ownership

| Responsibility | Suggested owner |
|---|---|
| Metrc Settings, credentials | IT / System Administrator |
| Daily parked-item triage | Compliance Officer |
| Variance investigation | Inventory / Compliance |
| Item master flags | Master Data owner |
| Tag ordering and receipt | Inventory Manager |

---

## 12. Testing and UAT

### Automated smoke test

An automated end-to-end test ships with the module. It creates a real transaction
chain against the Metrc sandbox, verifies eleven behaviours, and removes everything
it created.

**Result: 11 of 11 checks passed.**

| # | Check | Result |
|---|---|---|
| 1 | Tag quantity updates from the stock ledger | Pass |
| 2 | Variance calculated | Pass |
| 3 | Sales Invoice queues on submit | Pass |
| 4 | Queue entry created | Pass |
| 5 | Sale time formatted as facility-local | Pass |
| 6 | Correct package tag reported | Pass |
| 7 | Invoice number sent as the external reference | Pass |
| 8 | Unit of measure valid for Metrc | Pass |
| 9 | Queue processes successfully | Pass |
| 10 | Status written back to the invoice | Pass |
| 11 | Re-submitting does not duplicate the report | Pass |

Check 11 matters more than it looks: Metrc has no duplicate protection of its own,
and a duplicate sales receipt in a state system is a compliance incident.

### UAT scenarios for the business

| # | Scenario | Expected result |
|---|---|---|
| U1 | Sell a tracked product with a tagged batch | Invoice shows **Synced**, Receipt ID populated |
| U2 | Sell a non-tracked product | Invoice shows **Not Tracked** |
| U3 | Sell a tracked product with no batch | Submission blocked, message names the row |
| U4 | Cancel a synced invoice | Deletion queued |
| U5 | Reconcile stock down by 20g | Adjustment of −20g reported |
| U6 | Reconcile with no reason set | Default reason applied, still succeeds |
| U7 | Deliver to a customer with no licence | Blocked with explanatory message |
| U8 | Deliver to a licensed customer | Transfer template appears in Metrc |
| U9 | Sell a batch with a failed lab result | Red **Lab: FAILED** badge visible on the Batch |
| U10 | Use an unmapped unit of measure | Blocked, message names the unit |
| U11 | Manufacture with an empty tag pool | Blocked with a clear message |
| U12 | Force a failure, then press Resync | Recovers to **Synced** |

### Recommended UAT approach

Run in **Sandbox** with **Dry Run on** first — this exercises every validation and
lets the team read the exact payloads without touching a state system. Then turn
Dry Run off, still in Sandbox, and confirm the data appears in the Metrc test
portal.

---

## 13. Project status and RAID log

### Delivery status

| Workstream | Status |
|---|---|
| Technical design | Complete — 50-page technical guide delivered |
| Core integration | Complete |
| Sales, delivery, stock, manufacturing flows | Complete |
| User interface and reporting | Complete |
| Automated testing | Complete — 11/11 |
| Sandbox validation | Complete |
| Production validation | **Blocked** — external dependency |
| End-user training | **Not started** |
| Production cutover | **Not started** |

### Risks

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| **R1** | Server timezone is `America/Adak`, not Pacific. Sale times would be reported two hours out, moving evening sales to the wrong day. | **High** — systematic misreporting | **Certain** if unaddressed | Correct System Settings before enabling push. Verified reproducible in testing. |
| **R2** | Metrc production access not granted. | **High** — blocks go-live | Known | Apply to Metrc, demonstrate the sandbox integration. Owner: project sponsor. |
| **R3** | Scheduler paused; nothing syncs automatically. | Medium | Certain | Enable when the business is ready for continuous sync. |
| **R4** | Items not yet flagged as tracked, so nothing reports. | Medium | Certain | Master-data exercise before UAT. |
| **R5** | Users fill in Batch but not Muid, making stock invisible to compliance. | **High** — silent under-reporting | Likely without training | Cover in training; consider a validation rule. |
| **R6** | Sandbox test data (~9,700 tags) sits in the staging database. | Low | Occurred | A purge routine is provided; run before production cutover. |
| **R7** | Metrc rate limits depend on our contract tier, which is not yet confirmed. | Medium | Unknown | Confirm the tier with our Metrc representative. |

### Assumptions

- Products sold to licensed businesses; retail sales default to "Consumer" customer type.
- One Warehouse maps to exactly one Metrc licence.
- Tags are ordered and received in Metrc before ERPNext needs them.
- Physical counts remain the authority in a dispute between the two systems.

### Issues

| ID | Issue | Owner |
|---|---|---|
| I1 | No Warehouse currently carries a production METRC License # | Functional consultant |
| I2 | Customer licence numbers not populated for all trade customers | Sales / Master data |
| I3 | Metrc contract tier and webhook availability unconfirmed | Project sponsor |

### Dependencies

- Metrc production integrator approval (external, unscheduled)
- Server timezone correction (internal, affects all users)
- Master-data cleanup: item flags, customer licences, warehouse licences

---

## 14. Go-live plan

Five phases. Each has an exit criterion that must be met before the next begins.

### Phase 1 — Read-only on production data *(1–2 weeks)*

Point at production in read-only mode. Pull real inventory and reconcile.

**Exit:** variance report reviewed and understood; discrepancies explained.

This phase delivers value on its own — it tells you, for the first time, exactly
where the two systems disagree, with no risk of writing anything.

### Phase 2 — Dry run *(1–2 weeks)*

Turn push on with Dry Run enabled. Real documents generate real payloads that are
logged but not transmitted.

**Exit:** payloads reviewed and correct; **timezone confirmed fixed**; no validation
errors.

### Phase 3 — Sandbox writes *(1–2 weeks)*

Transmit for real, still to the test environment. Full UAT.

**Exit:** all UAT scenarios pass; no parked items for a full week.

### Phase 4 — Metrc approval *(external, unknown duration)*

Apply, demonstrate the integration, receive production credentials. Confirm rate
limits and webhook availability.

**Exit:** production credentials issued and connection tested.

### Phase 5 — Production, one facility at a time

Rotate all development credentials. Run read-only on production first, then dry
run, then live for a single facility. Monitor daily for two weeks before adding
facilities.

**Exit:** all facilities live; parked count consistently zero.

> **Do not skip the read-only step on production.** Sandbox data is synthetic;
> real operational data will surface differences no test facility can.

---

## 15. Decisions needed from the business

| # | Decision | Owner | Blocks |
|---|---|---|---|
| **D1** | Correct the server timezone to `America/Los_Angeles`? Affects every timestamp shown to every user, so it needs a communicated change window. | IT + Operations | Phase 2 exit |
| **D2** | Who owns daily parked-item triage? | Operations | Training |
| **D3** | Which Warehouses map to which Metrc licences? | Functional consultant | Phase 1 |
| **D4** | Which items are Metrc-tracked? | Master data + Compliance | Phase 1 |
| **D5** | Enable the scheduler, or keep sync manual during UAT? | Project manager | Phase 1 |
| **D6** | Who receives compliance alert emails? | Compliance | Phase 1 |
| **D7** | Log retention period — is 120 days sufficient for our licence type? | Compliance | Phase 5 |

**D1 is the critical path item.** It is small, it is not a development task, and
nothing can go live correctly until it is resolved.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **Metrc** | California's mandatory cannabis track-and-trace system |
| **Metrc Connect** | The portal where software vendors manage integrator keys |
| **Integrator key** | Company-wide key identifying our software to Metrc |
| **User key** | Per-user key; permissions follow that Metrc user |
| **Facility** | A licensed location in Metrc; our Warehouse |
| **Package** | A tagged quantity of product; our Batch |
| **Tag** | The printed state label with a unique number |
| **Muid** | The ERPNext field carrying the tag onto stock transactions |
| **Manifest** | The transport document for moving product between licensees |
| **Sandbox** | Metrc's test environment; no compliance consequence |
| **Outbox** | Our queue of instructions waiting to be sent to Metrc |
| **Parked** | A queued instruction that failed permanently and needs a human |
| **Variance** | A difference between Metrc's quantity and our stock ledger |
| **Cursor** | A bookmark recording how far a sync has progressed |
| **Dry run** | Mode that builds payloads and logs them without transmitting |

---

## Appendix A — Field reference

Fields added by this project. All are system-maintained and read-only unless noted.

### Item

| Field | Purpose |
|---|---|
| METRC Tracked | **User-set.** Master switch for reporting this product |
| METRC Item Name | **User-set.** Must match Metrc exactly |
| METRC Item Category | Product category in Metrc |
| METRC Item ID | Metrc's internal identifier |
| METRC UOM | Unit Metrc holds this item in |
| METRC Last Synced | Last confirmation from Metrc |

### Batch

| Field | Purpose |
|---|---|
| METRC Tag | *(pre-existing)* The package label |
| METRC Package ID | Metrc's internal identifier |
| METRC Package Status | Active, On Hold, In Transit, Finished |
| METRC Quantity | What Metrc believes we hold |
| METRC UOM | Unit of that quantity |
| METRC Variance | Our ledger minus Metrc |
| METRC Lab Result | Passed, Failed, Not Tested |
| METRC Lab Result Date | When testing completed |

### Sales Invoice

| Field | Purpose |
|---|---|
| METRC Sync Status | Not Tracked / Queued / Synced / Failed / Parked |
| METRC Receipt ID | Metrc's receipt identifier |
| METRC License # | Facility the sale was reported under |
| METRC Synced On | Timestamp of the last attempt |
| METRC Message | Plain-language failure reason |

### Delivery Note

| Field | Purpose |
|---|---|
| METRC Sync Status | As above |
| METRC Transfer ID | Metrc's transfer identifier |
| METRC Manifest # | The manifest number, once created |
| METRC Transfer Type | **User-set.** Defaults to "Transfer" |
| METRC License #, Synced On, Message | As above |

### Stock Reconciliation

| Field | Purpose |
|---|---|
| METRC Correction Made | *(pre-existing)* Flags this as a compliance correction |
| METRC Adjustment Reason | **User-set.** Must be a valid Metrc reason |
| METRC Sync Status, Synced On, Message | As above |

### Warehouse

| Field | Purpose |
|---|---|
| METRC License # | *(pre-existing)* **User-set.** The licence this warehouse represents |
| METRC Facility Name | Confirmed name from Metrc |
| METRC Last Synced | Last confirmation |

### Work Order

| Field | Purpose |
|---|---|
| METRC Processing Job Type | **User-set.** Must match a Metrc job type |
| METRC Processing Job ID | Metrc's job identifier |
| METRC Sync Status | As above |

---

## Appendix B — Status reference

### Document sync status

| Status | Colour | Meaning | Action |
|---|---|---|---|
| *(blank)* | — | Not yet evaluated | None |
| Not Tracked | Grey | No tracked items | None |
| Queued | Orange | Waiting to send | None — clears within 5 min |
| Synced | Green | Accepted by Metrc | None |
| Failed | Red | Temporary problem, retrying | Watch |
| Parked | Red | Permanently failed | **Fix and Resync** |

### Metric Tag status

| Status | Meaning |
|---|---|
| Unused | Received from Metrc, not yet assigned |
| Active | Assigned to a package holding stock |
| Empty | Package depleted or finished |

### Metrc package status

| Status | Meaning |
|---|---|
| Active | In inventory and available |
| On Hold | Restricted by the state — cannot be sold |
| In Transit | On a manifest, moving between facilities |
| Finished | Depleted or discontinued |

---

## Where to go next

| Need | Document |
|---|---|
| Technical detail, API specifics, code | `METRC_INTEGRATION_GUIDE.md` / `.pdf` (50 pages) |
| Configuration | §10 of this document |
| UAT scripts | §12 of this document |
| Project reporting | §13 and §14 of this document |

*End of document.*
