# Credit & AR Control

Credit is treated as an unsecured loan. Every customer is **COD by default**.
Terms exist only behind a documented credit file, a signed Credit Agreement and
written MD approval. This module is the enforcement layer.

Module: `Credit and AR` · App: `cannabis_management` · Frappe/ERPNext v15 · Python 3.11

---

## Decision log

These were confirmed before any code was written. They override the source
policy document where the two disagree.

| # | Decision |
|---|---|
| 1 | **Every non-COD payment terms template** requires a written MD exception reason on the Credit Application. |
| 2 | Finance charges apply to **all past-due terms invoices**, not NET30 only. |
| 3 | 50%-down terms: the deposit must be **cleared** before production/staging. Only the deferred half counts against the credit line. |
| 14 | **Cash orders are outside the policy** (2026-08-18). Mode of Payment = Cash On Delivery ⇒ no approval, no credit line, no deposit, no print block, **and no hold** — on the order and on Delivery Notes raised from it. ERPNext's own defaults stand, including `payment_terms_template`. Rationale: cash carries no exposure, and 109 customers sat on Hard Hold unable to trade even for cash. **Exception:** the workout paydown still applies to cash, so a workout customer cannot escape the paydown by switching every order to cash. |
| 4 | Sample orders are zero-value but **stock still leaves inventory**. No reason code, no monthly cap, and **holds do not block samples**. |
| 5 | **Per-order MD approval, always.** A live credit line does not auto-pass future Terms orders. |
| 6 | **Single group-wide line** shared across TSBC Ranch, Motley Terpz and Master Touch Manufacturing. |
| 7 | **No intercompany *trading* handling** — no `Intercompany` Customer Group is created and no Customer Group is reassigned. The five Customer records that are our own operating entities (`Motley Terpz`, `TSBC Ranch`, `Master Touch Manufacturing`, `MTPZ`, `LA Canna`) carry `custom_is_intercompany = 1` and are excluded from every report **and from the company metrics** — see below. |
| 8 | Weekly volume (1,000 g / 100 lbs) is a **reporting and scoring input only** — it never gates an application. |
| 9 | Scoring model as specified in §15, weights held as module constants. |
| 10 | **Ops Manager and Managing Director can both approve** Terms orders. Ops = `muhammad@motleyterpz.com`, MD = `imran@motleyterpz.com`. |
| 11 | Bounced payments are identified by an **explicit flag on Payment Entry**, not by inferring intent from any cancellation. |
| 12 | At go-live **every customer resets to COD**. No informal terms are migrated. |
| 13 | The `total_ar_cap` freeze governs the **new book only**. Legacy is reported separately and does not freeze the company. |
| 14 | **Existing fields are reused, not duplicated** — see below. |
| 15 | `policy_effective_date` ships **blank**; every scheduled job is inert until Finance sets it. |
| 16 | CEO and Collections Officer routing slots ship blank; empty routes are skipped and logged, never thrown. |

### Why the cap is new-book only

At the time of build the site carried **$4.77M** of open AR (TSBC $2.89M,
Motley $1.67M, MTM $200k) against a $400k cap, with the earliest invoice dated
2025-11-24. Counting legacy toward the cap as §12 literally states would leave
the company permanently frozen from the first day, making the freeze engine
meaningless. The cap therefore governs post-`policy_effective_date` AR; legacy
appears in the Legacy Recovery Register and in the Friday report as its own
line.

---

## The policy exemption

`Customer.custom_credit_policy_exempt` is the single switch that carves an
account out of this module entirely. Tick it and **nothing here touches the
account**:

| Engine | Behaviour when exempt |
|---|---|
| Sales Order gate | Skipped — no COD forcing, no line check, no approval round-trip, no print block, no deposit. Terms may be used with no credit line at all. |
| Gate 1 (SO / DN / WO / SE) | Never fires |
| Daily sweep, immediate holds | Customer skipped; **no AR Case can be created** for them — `create_case` and `raise_immediate_hold` both refuse |
| Returned payment, limit breach, broken PTP, expired license | No hold raised |
| Payment Entry two-ledger rule | Not enforced |
| Payment plans, workouts | Skipped by the daily jobs |
| Finance charges | Never assessed |
| Payment scoring | Not scored |

**What it deliberately does *not* do is hide the money.** Their AR still counts
toward the company-wide cap, DSO and CEI, and they still appear on the reports —
otherwise exempting the largest debtor would quietly switch off the freeze
engine for everyone. That is the one asymmetry worth knowing about; say the word
if you want exempt balances out of the metrics too.

The flag sits at **permlevel 1**, alongside the approved terms template, so only
`Credit Finance` and the `Managing Director` can grant it — an exemption Sales
could tick itself would defeat the module. `custom_credit_policy_exempt_reason`
is mandatory whenever it is on, and every toggle is written to the Customer's
comment trail.

Ticking it sets `custom_credit_status = "Policy Exempt"` and **clears the live
hold flags**. That is deliberate: `enforce_hold` already ignores exempt
accounts, so a lingering "Hard Hold" badge would be a flag that blocks nothing —
the worst kind, because people trust it. Un-ticking hands the account straight
back to the engines; the next daily sweep re-raises whatever is warranted.

The flag is read live by every engine via `utils.is_policy_exempt()`, so
toggling it needs no migration and takes effect on the next save.

---

## Field reuse

The module introduces no second order-type or payment-mode field. Three fields
already existed on Sales Order and already drive live print formats, list views
and dashboards:

| Existing field | Values | Role in the credit gate |
|---|---|---|
| `custom_sales_order_type` | Sales / Samples / Events / Testing / Influencers / Consignment / Tolling | `Samples` ⇒ order type **Sample** |
| `custom_mode_of_payment` | Cash On Delivery / Payment Terms | `Payment Terms` ⇒ order type **Terms**; anything else ⇒ **COD** |
| `custom_approval_status` | Pending Approval / Approved / Rejected | The MD/Ops approval round-trip; `Not Required` is added to the option list |

`utils.resolve_order_type(doc)` is the single place this mapping lives. Sample
wins over payment mode — a zero-value sample is never a credit decision. The 216
historical Sales Orders with a blank payment mode read as COD.

On Customer, `custom_license_number`, `custom_license_expiry` and
`custom_license_type` already existed and are reused. `custom_license_verified`
is new and means *verified as part of the credit file*, which is deliberately
distinct from the existing METRC verification flag.

On Sales Invoice, `custom_mode_of_payment` (Data, read-only, effectively unused)
is reused to carry the order's payment mode forward from the Sales Order.

**Consequence:** the pre-existing approval flow in
`overrides/sales_order_restrictions.py` — which emails a hard-coded address and
lets the `HOO` role auto-approve on submit — is superseded in Phase 3. That
`HOO` role is currently held only by developer accounts.

---

## Architecture

Four new DocTypes, everything else native.

| DocType | Kind | Phase |
|---|---|---|
| `Credit Policy Settings` | Single | 1 |
| `Credit Application` | Submittable + Workflow | 2 |
| `AR Case` | Status-driven, not submittable | 4 |
| `AR Case Installment` | Child of AR Case | 4 |

Reused natively: `Customer Credit Limit`, `Payment Terms Template`, `Contact`,
`File`, `Communication`, `Workflow`/`ToDo`/`Notification`, the core Accounts
Receivable report, `GL Entry`, and `Sales Invoice.outstanding_amount`.

### File layout

```
credit_and_ar/
├── doctype/credit_policy_settings/   Single DocType (Phase 1)
├── doctype/credit_application/       Submittable + workflow (Phase 2)
├── custom_fields.py                  Custom Field definitions, applied by patch
├── masters.py                        Roles, payment terms ladder, item, permlevels
├── workflow.py                       Credit Application Approval workflow
├── credit_engine.py                  Exposure, available line, past-due snapshot
├── utils.py                          Settings cache, order-type vocabulary, UOM, routing
└── README.md
```

---

## Credit Application

One document is the credit file, the onboarding form, the agreement register,
the MD approval record and the source for the Terms & Credit Line Register.
Naming `CREDIT-APP-.YYYY.-.#####`.

### Workflow — `Credit Application Approval`

| State | Docstatus | Who acts | Action → next |
|---|---|---|---|
| Draft | 0 | Sales User, Credit Finance | `Submit for Review` → Finance Review |
| Finance Review | 0 | Credit Finance | `Recommend` → Pending MD Approval · `Reject` → Rejected |
| Pending MD Approval | 0 | Managing Director | `Approve` → Approved · `Reject` → Rejected |
| Approved | 1 | — | `Revoke` → Revoked (Credit Finance or MD) |
| Rejected / Expired / Revoked | 1 | — | terminal |

`Expired` is set by the daily scheduler, not by a user transition.

### Gates

Each gate asks only for what the person at that gate can actually supply.

**Submit for Review** — the applicant's own submission — requires the **AP
contact**: name, direct line and email. This is the customer's information, so
it is collected when they hand the form in rather than chased at the last gate,
where it would stall the decision instead of the paperwork. The rule runs
server-side on `validate`, so it applies identically to the desk form and to a
Web Form.

**Recommend** requires: legal buyer, entity type, license number and expiry, a
*verified* and unexpired license, expected volume and revenue, a positive
recommended limit, recommended terms, and enhanced assessment notes whenever the
limit exceeds `enhanced_review_threshold`.

*Payment History Summary* and *Financial Capacity Notes* are still on the form
but are **not** enforced — Finance often recommends before the narrative is
written up.

The application carries **no company field**. The line is group-wide, so where a
company is still needed — mirroring the native `Customer Credit Limit` row,
stamping an AR Case — it is derived from the customer's own trading history via
`utils.company_of()` rather than asked for again.

**Approve** requires all four clauses confirmed (finance charge, collection
cost, counsel-approved, reconciliation), the onboarding form, a positive
approved limit, terms within `max_terms_days`, and a written exception reason —
which, per decision ①, means **every non-COD term**.

It does **not** require the signed agreement. The MD approves the *decision*;
the countersigned agreement is a separate condition precedent (below).

Both gates raise one **consolidated** error listing everything outstanding,
never one item at a time.

### AP contact rules

* **Email** — shared inboxes are rejected outright: `info@`, `ap@`, `accounts@`,
  `accounting@`, `billing@`, `admin@`, `office@`, `sales@`, `support@`,
  `finance@`, `payables@`, `invoices@`, `noreply@` and separator variants
  (`a.p@`, `accounts-payable@`).
* **Phone** — must be a direct line. Anything ending in an extension marker
  (`ext 204`, `x204`, `extension 204`) or carrying fewer than 10 digits is
  rejected. A direct line already on file for another customer raises a
  non-blocking warning suggesting a shared **Credit Group Parent**.

### Approval goes live immediately

The MD's approval is the gate on its own. **Terms go live on submit**,
whether or not the countersigned Credit Agreement is on file yet.

* Approve with the agreement already on file → terms go live, as before.
* Approve without it → terms **still** go live on submit (limit, terms
  template and status are written to the Customer), and the owner, the AP
  contact and Finance are emailed that the signed Credit Agreement is still
  outstanding — a paperwork reminder, not a hold on the line.
* `credit_agreement_signed`, `credit_agreement_document` and
  `agreement_signed_date` are `allow_on_submit`, so the agreement can still be
  attached after approval to close out the file; it no longer changes whether
  the line is usable.

`credit_engine.get_active_credit_application()` returns the application the
moment it is Approved and submitted, agreement or not.

### What going live does

1. Retires any other approved application in the same credit group — **one live
   line per group**, with the superseded record marked `Revoked` and commented.
2. Upserts the native `Customer Credit Limit` row for customer + company with
   `bypass_credit_limit_check = 0`.
3. Writes `custom_active_credit_application`, `custom_approved_credit_limit`,
   `custom_credit_terms_template`, `custom_terms_valid_until`,
   `custom_credit_status = "Terms Approved"`, `custom_reconciliation_clause_ack`,
   the license fields and the AP contact onto the Customer, and sets
   `payment_terms`. The **limit also lands on the group parent**, because the
   engine reads the line from there.
4. Emails the owner, the AP contact, Finance and Sales Managers.

A customer already on **hold** keeps their hold status — approving a line does
not lift a stop-work order.

Revoke, expire and cancel all run the inverse: terms template cleared, status
back to `COD`, limit zeroed on both the customer and the native credit-limit
row, open Terms Sales Orders pushed back to `Pending Approval`, and Finance,
Sales and the MD notified.

`effective_from` defaults to today and `valid_until` to 90 days later —
the quarterly review.

### Scheduler

`expire_credit_lines` runs daily (07:00 UTC, with the existing AR reminders):
retires lines past `valid_until` and emails Finance a 15-day expiry warning
list. Inert until `policy_effective_date` is set.

### The native Customer Credit Limit row

The approved limit is mirrored onto ERPNext's own `Customer Credit Limit` child
row, but with **`bypass_credit_limit_check = 1`** — it is a mirror for
reporting, not a second enforcement layer. Three reasons:

* it is per-company, so it cannot see group exposure;
* it cannot see a cleared over-limit deposit, so it rejects orders this module
  has legitimately cleared;
* its error message invites Sales to ask a named list of users to *raise the
  limit* — exactly the behaviour the Credit Application process exists to stop.

ERPNext also refuses to lower that row below the customer's current outstanding,
which would make it impossible to revoke a line from the customer who most needs
it revoked. The row is therefore written directly rather than through
`Customer.save()`.

---

## The Sales Order gate

Order type is derived, never entered twice:

```
Samples                       →  Sample
Payment Terms (not a sample)  →  Terms
anything else, incl. blank    →  Cash   (Mode of Payment = Cash On Delivery)
```

**Cash is outside the policy entirely.** The money arrives with the product, so there
is no exposure for the policy to protect — see decision 14.

### On save — nothing blocks a draft

| Type | What happens |
|---|---|
| **Cash** | Nothing. Approval `Not Required`, print unblocked, no deposit, no credit line — and the document is otherwise left to ERPNext: `payment_terms_template` and `payment_schedule` are **not** touched. No credit checks, and **holds do not block cash orders**. |
| **Sample** | Every rate, discount and margin forced to **0**, totals recalculated, then a hard assertion that the grand total is zero. Terms cleared. No credit checks, and **holds do not block samples**. |
| **Terms** | Computed and stamped — available line, required deposit, approval status, print block — plus an **orange warning** listing everything that will stop the order at submit. |

A Terms order **always saves**. Sales need to be able to write an order down
while the credit file is still being put together; the policy only has to bite
before the order is committed. The save-time warning and the submit-time refusal
are generated from **the same list** (`_terms_problems`), so the two can never
drift apart.

### What stops a Terms order at submit

Workout accounts are refused outright · a payment terms template is required ·
the customer must have a live, unexpired, unrevoked credit line (the error names
the exact blocker) · the template must match the one approved for the account,
§5 one-term-per-account · the term must be within `max_terms_days` · a payment
plan must be healthy · Hard Hold and Immediate Hold refuse, Warning only warns ·
a company freeze refuses for everyone, good standing included. All of it is
re-run **live** at submit, because holds, freezes and credit lines move between
drafting an order and committing it — and every reason is listed in one
consolidated error, not one at a time.

### Required deposit

Two independent reasons to take money up front, **added together**:

1. the template's own up-front leg — the 50% of a `50% down NETnn` term;
2. §4 over-limit — the amount by which the order's *credit* exposure exceeds the
   available line.

Only the deferred portion of a 50%-down order is credit, so only that portion is
measured against the line. There is **no single-order exception at any amount**.

### On submit

Terms orders throw unless `custom_approval_status == "Approved"`. Holds and the
freeze are **re-checked at submit**, because state can have moved since the
order was saved. Any required deposit must be **cleared** — a `Deposit` Payment
Entry against this order, submitted, and either carrying a clearance date or
paid by an instant (Cash-type) mode of payment. A deposit that has not cleared
is a promise, not a payment.

### Approval round-trip

`api.request_terms_approval` → status `Pending Approval`, print blocked, ToDos
for the MD and Ops Manager, and an email carrying customer, amount, terms,
exposure, available line, payment score and the credit application link.

`api.approve_terms` / `api.reject_terms` are guarded server-side against
`Managing Director`, `Ops Manager` and `System Manager` — the client buttons are
convenience, never the control. Rejection **keeps print blocked**: a rejected
Terms order must not leave the building.

Per decision ⑤ this happens for **every** Terms order, every time. An approved
credit line grants the *ability* to order on terms, not a standing approval.

### Print blocking

Client-side menu removal is cosmetic. The block is enforced in
[print_guard.py](print_guard.py), registered via `override_whitelisted_methods`
in front of all four routes that can render a document —
`printview.get_html_and_style`, `print_format.download_pdf`,
`weasyprint.download_pdf` (Print Designer) and `communication.email.make` when a
print format is attached. Every other DocType passes straight through.

### Known permission gaps

`payment_terms_template` and `payment_schedule` are behind **permlevel 1**, with
read+write granted to `Credit Finance` and `Managing Director`. But **`Sales
Manager` already held a permlevel-1 DocPerm on Sales Order**, and `Sales Master
Manager` holds one on Customer. Both predate this module and both defeat §1
("Sales must not be able to set terms"). They were not removed unilaterally —
decide whether to strip them.

---

## Stop Work — the hold engine

One DocType, `AR Case`, covers every stop-work state: `Warning`, `Hard Hold`,
`Immediate Hold`, `Payment Plan` and `Workout` are case *types*, not separate
DocTypes. Not submittable — the scheduler creates and updates these, and
`Version` carries the audit trail.

### Two clocks

**The daily sweep** (`evaluate_customer_credit_status`) reads live past-due
figures for every non-intercompany, non-disabled customer:

| Condition | Result |
|---|---|
| Any amount past due | **Warning** — work continues, the clock is running |
| Oldest invoice past `hard_hold_days` (5) **or** past due at or above `hard_hold_amount` ($1,000) | **Hard Hold**, whichever comes first |
| Past due cleared | Case **Cured**, customer flags cleared |

**Event-driven immediate holds** cannot wait for tomorrow:

| Trigger | How it fires |
|---|---|
| Returned payment | `Payment Entry.on_cancel` **only when `custom_is_returned_payment` is ticked**. An ordinary correction raises nothing — inferring a bounce from any cancellation would fire holds on routine re-keying. Increments `custom_returned_payment_count`. |
| Broken promise to pay | Daily — a `promise_to_pay_date` that passed with the balance still outstanding. Increments `custom_broken_ptp_count` and clears the promise so it is not counted twice. |
| Expired license | Daily, with warnings at T-30 and T-7 |
| Limit breach | `Sales Invoice.on_submit`, when group exposure passes the approved limit |
| Suspected fraud / insolvency | Manual, via `api.raise_manual_case` — Finance or MD only |

**The sweep only ever moves cases it could have created itself.** A case a human
released or defaulted is never quietly reopened or cured by a scheduler, and a
Hard Hold is never auto-downgraded to a Warning — Finance releases holds, not
the clock.

### Gate 1

`hold_engine.enforce_hold` is wired to `before_submit` on **Sales Order**,
**Delivery Note**, **Work Order** and **Stock Entry**. A Hard Hold or Immediate
Hold stops all four.

* **Quotation is never gated** — quoting a delinquent customer costs nothing and
  keeps the conversation alive.
* **Sample orders are exempt**, per decision ④.
* Stock Entries are gated only for `Material Transfer for Manufacture` and
  `Manufacture`; receipts and repacks are untouched.
* Work Orders and Stock Entries resolve their customer through the linked Sales
  Order.

**A hold blocks COD orders too.** This is the literal §7 reading — "no new work
until cured" — and it is the leverage. If COD trade should continue for a held
customer, say so and it is a one-line change.

### Release

`api.release_ar_case` is guarded to **Credit Finance**, and every basis is
verified live at the moment of release, not trusted from the form:

| Basis | Verified |
|---|---|
| Paid in Full | Past due recomputed live; any remaining balance refuses the release |
| Current on Approved Plan | An active plan must exist, be **MD-ratified**, and have zero missed installments |
| MD Exception | Notes are mandatory; logged to the case as an exception-register comment and emailed to MD, CEO and Finance |

Editing `status` to `Released` on the form throws — the release action is the
only path, so the basis is always verified and recorded.

### Customer roll-up

A customer can carry several cases at once. `sync_customer_from_cases`
recomputes `custom_on_hold`, `custom_hold_type`, `custom_hold_since`,
`custom_active_ar_case` and `custom_credit_status` from whichever live case
ranks highest: Immediate Hold > Hard Hold > Workout > Payment Plan > Warning.
With no live case, the status falls back to `Terms Approved` or `COD` depending
on whether a credit line is live.

---

## Payment plans — two ledgers, never netted

A customer on a plan runs two books at once: the **plan** (old debt being worked
off) and the **new book** (current trading). Money for one must never quietly
pay down the other — that is how a plan collapses while the reports still look
healthy.

### Creating a plan

Only **Credit Finance** can put an account on a plan. On save it must carry the
signed document, a signed date, a positive principal, and a schedule whose rows
sum to the principal with every date in the future. A plan is not usable until
`md_ratified` — and only the Managing Director can tick it.

**Ratification freezes the boundary.** At that moment every **past-due** invoice
is stamped `custom_ledger = "Plan"` and `custom_ar_case = <the plan>`. An
invoice still inside its terms is current trading and stays on the new book. If
the captured balance differs from the plan principal, the case is commented so
Finance can see it.

### The rule

| Receipt ledger | May allocate to |
|---|---|
| `New Book` | New Book invoices only — never a plan invoice |
| `Legacy` | Legacy invoices only |
| `Plan` | Plan and Legacy invoices belonging to *this* plan |
| `Deposit`, `Workout Paydown` | **Nothing** — these sit against a Sales Order until it is invoiced |

Any cross-ledger allocation throws. The ledger is **derived** when left blank —
from the allocated invoices, or `Deposit` when the receipt names a Sales Order —
so existing automation that creates Payment Entries keeps working while every
customer receipt still ends up classified.

On the form, auto-allocation is **switched off** for plan customers: it would
happily spread one receipt across both books.

### Default

A `Plan` receipt settles the named installment, or the oldest one still owing.
Cancelling it puts the schedule back. Daily, any `Pending` installment past its
due date becomes `Missed`, increments the counter, and raises an **Immediate
Hold** with trigger `Plan Default` — *one missed payment is an immediate hard
hold on all new work until cured*.

New terms work for a plan customer requires **all four**: the plan is ratified,
zero missed installments, a *separate* Credit Application exists, and it is
Approved. Otherwise the account is COD only and plan payments continue as
scheduled.

The plan engine and the past-due engine run **independently**. A new invoice
going late is its own stop-work event regardless of plan status, and plan
default holds everything regardless of the new book. Neither suppresses the
other.

---

## Workout accounts

Only the Managing Director designates one, and `workout_reason` is mandatory.
The starting balance is captured at designation.

* **Terms are refused outright** — COD or prepaid only, zero new unsecured
  exposure, no exceptions.
* Every order carries a **paydown**: `paydown_percent × order value` (default
  15%) or a fixed amount. Submit throws until a **cleared** `Workout Paydown`
  Payment Entry covers it. *No paydown, no product.*
* Daily the balance is recomputed. `recovered_to_date = starting − current`, and
  the trend is set from the previous reading.
* **The balance only moves down.** If it ever rises above where it started, the
  workout is `Defaulted`, a Hard Hold case opens, and the MD and Finance are
  emailed.
* If it has not shrunk within `workout_no_shrink_days` (60), the case is flagged
  for final demand and collections.

---

## Metrics and the company freeze

Three numbers decide whether the group may extend any new unsecured exposure,
measured over a rolling **30-day** window, **new book only**:

| Metric | Definition | Breach |
|---|---|---|
| Total AR | New-book outstanding, from the ledger | above `total_ar_cap` |
| DSO | `credit_AR / credit_sales × 30` | at or above `dso_breach_days` (30) |
| CEI | `(Beginning AR + Credit Sales − Ending Total AR) / (Beginning AR + Credit Sales − Ending Current AR) × 100` | below `cei_breach_below` (85%) |

A **credit sale** is one actually extended on terms — read from the payment mode
carried over from the Sales Order, falling back to the payment terms template.
COD invoices, samples and finance charges are all excluded, so an unpaid COD
invoice cannot inflate DSO.

Beginning and ending balances come from **GL Entry**, not
`Sales Invoice.outstanding_amount`, because CEI needs the balance as it stood at
the start of the period and the invoice field only ever knows *now*.

Metrics are computed **group-wide and per company**; the freeze is driven by the
group figure, and the per-company breakdown is stored for trending.

**Intercompany is excluded from the metrics, not just the reports.** A balance
between two of our own companies is not unsecured customer credit; leaving it in
added $2.5M and would have tripped the cap on money the group owes itself.
`utils.intercompany_customers()` is the single source for that exclusion — it
reads the `custom_is_intercompany` flag, plus the optional
`intercompany_customer_group` setting if one is ever configured.

### Freeze

On breach: `company_freeze_active = 1`, the reason recorded, and MD, CEO,
Finance and all Sales Managers emailed immediately. Every Terms order is then
refused at validate and submit — **including good-standing accounts**. Existing
invoices keep their agreed due dates; new orders must be re-typed COD or prepaid.

**Nothing lifts silently.** When the metrics return inside their thresholds the
daily job only emails Finance to say the freeze *may* be lifted. Two paths out:

* `confirm_unfreeze(notes)` — Credit Finance, in writing. Re-measures live and
  refuses while any metric is still breached.
* `unfreeze_override(reason)` — the exception path. Requires **both** the
  Managing Director and the CEO to sign off; the first call records a sign-off
  and raises a ToDo for the other. Both signatures lift the freeze and the
  override is logged to the exception register with the metrics still breached
  called out explicitly.

Every lift writes a Comment against Credit Policy Settings — that is the
exception register.

### Snapshots

A daily JSON snapshot (group totals, per-company breakdown, breaches) is kept in
a **global default**, retained 400 days — no new DocType, per the architecture
constraint. Read it with `metrics.get_metrics_history()`.

---

## Finance charges

Monthly, on the 1st at 06:00 UTC. Simple, non-compounding, pro-rated by day from
the **day after** the due date, at `min(monthly_rate, max_lawful_rate)`.

Two exclusions that are legal rather than arithmetic:

* **Legacy invoices are never charged** — §12, collected on original terms with
  no retroactive fees.
* **No charge under an agreement missing the counsel-approved clause.** With
  `require_counsel_approved_clause` on, a customer whose approved Credit
  Application lacks `counsel_approved_clause` is skipped entirely.

One invoice per customer per run, one line per underlying invoice, each line
naming the source invoice, the principal, the rate and the days. Every source
invoice is stamped `custom_finance_charge_applied_upto` so **a repeated run
never charges the same days twice**. Left in Draft unless
`auto_submit_finance_charges` is on.

Finance charge invoices are excluded from DSO, CEI and the payment score — a
late fee is a consequence of poor payment, not evidence of it.

---

## The payment score

350–800, daily, rolling 12 months, minimum 3 paid invoices. Every weight is a
module constant in [scoring.py](scoring.py) so the model can be retuned without
touching logic.

| Component | Max | Basis |
|---|---|---|
| Base | 350 | floor |
| Payment timing | +250 | **value-weighted** mean of `settlement date − due date`, interpolated between anchors: −5d→250, 0d→210, +5d→150, +15d→70, +30d→20, +45d→0 |
| On-time consistency | +100 | % of invoices settled on or before the due date |
| Tenure & volume | +60 | 12-month relationship = 30, qualifying weekly volume = 30, both pro-rated below the threshold |
| Current standing | +40 | clean 40, warning 20, hold 0 |
| Penalties | −100 cap | returned payment −25 each, broken PTP −20, hard hold in last 6 months −25, plan default −50 |

Settlement dates come from the ledger — the last receipt allocated to the
invoice — because Sales Invoice records no payment date of its own. Timing is
value-weighted deliberately: a large invoice paid late says more than a small one.

**A note on "null" scores.** §15 asks for a null score below the minimum
invoice count, but Frappe creates Int columns as `NOT NULL DEFAULT 0`, so a null
cannot be stored. **`custom_score_band` is therefore authoritative**: a band of
`Insufficient History` means there is no score, and the stored 0 must be
rendered as "—".

Volume is normalised to grams through the item's UOM conversions
(1 lb = 453.59237 g) as a trailing four-week average, stored in both grams and
pounds so the report can show pounds for TSBC Ranch and grams for Motley Terpz
and Master Touch.

---

## Reports, workspace and notifications

Four **Script Reports** in the `Credit and AR` module, all excluding
intercompany accounts, all computing their AR aggregates in **one bulk query**
rather than per row — a per-customer round trip is fine for one Sales Order gate
but not across 250 customers on a report refresh.

| Report | What it answers |
|---|---|
| **Customer Credit Scorecard** | The MD's single source of truth for approving a line: score and band, signed avg days to pay, on-time %, weekly volume in lbs *and* grams, current AR, past due, approved limit, available line, utilisation, terms and expiry. Charted as a score distribution. |
| **Terms and Credit Line Register** | Every live line with the paperwork behind it — agreement and onboarding attachments as clickable links, reconciliation and counsel clauses, AP contact, approver, next review. Flags lines expiring within 15 days and any line **without the counsel clause** (no finance charges can be assessed on those). |
| **Red List** | Every past-due account flagged `HOLD` / `PLAN` / `WORKOUT` / `PAST DUE`, with promise-to-pay, last contact, next action and owner. The **Plan Book** totals — balance under plan, due vs. received this week — sit in the report message, with workout starting balance and recovery to date. |
| **Legacy Recovery Register** | Everything invoiced before the policy date, with recovered-this-week from the ledger. Every row states plainly that **no finance charges apply**, and the header repeats that legacy does not count toward the new-book cap. |

Colour is used to mean one thing only — a number that needs attention. Past due,
negative available line, a hold, an overdue promise and an expiring line all
render red; early payment and recovery render green.

### Workspace

`Credit and AR Control` carries eight **Number Cards** (new-book AR, cap
headroom, DSO, CEI, accounts on hold, pending MD approvals, freeze status,
legacy outstanding), shortcuts to the four reports and to three work queues
(applications pending MD, Terms orders awaiting approval, open AR cases), plus a
masters card.

Cards are `type = Custom` pointing at whitelisted methods in
[dashboard.py](dashboard.py) — no Dashboard Chart Source DocType, keeping to the
four-DocType constraint. **Note:** Number Card autonames from `label`, so the
label *is* the docname; the workspace references them by that exact string.

### Friday report

`weekly_report.send_weekly_report` runs Friday 08:00 UTC to the MD, CEO and
Finance. It assembles from the same engines the desk reports use, so the inbox
and the screen can never disagree: freeze banner, metrics vs. thresholds
(**new book and legacy always shown separately**), legacy recovered this week
and register balance, new AR extended split good-standing vs. distressed, the
AR/COD ratio of the week's sales, and the Red List with Plan Book totals. Preview
it any time with `weekly_report.build_report()`.

### Notification matrix

Most of §17 is emailed **directly by the engine that raises it**, because those
messages carry computed context an alert cannot express — exposure, available
line, score, release basis. [notifications.py](notifications.py) lists which
function owns each row, so there is one place to look.

What remains are six native `Notification` records for in-desk alerts that
benefit from the notification bell and per-user preferences: application pending
MD, application in Finance review, AR case opened, promise-to-pay due tomorrow,
workout review due, and credit line expiring. They ship as fixtures and can be
edited without a deploy.

---

## Testing

See [TESTING.md](TESTING.md) for the manual UI runbook. The automated suite for
phases 1–3 covers COD/Sample/Terms routing, the approval round-trip, all four
print routes, over-limit deposits, 50%-down maths, holds, freeze and workout
blocking.

---

## Exposure model

The line is **group-wide and revolving**. `credit_engine.get_line_summary()`
returns, for every Customer sharing a `custom_credit_group_parent`, across every
operating company:

* **Invoice outstanding** — all submitted Sales Invoices with a balance, new
  book *and* legacy. Money owed is money owed; the Legacy split governs the
  company freeze and finance charges, not a customer's own line.
* **Unbilled Terms orders** — submitted, not-fully-billed **Terms** Sales
  Orders, at the credit portion only. A COD order is not credit until it becomes
  an unpaid invoice, and the prepaid half of a 50%-down order was never at risk.
* Sample orders never count.

`available_line = approved_limit − total exposure`, and may legitimately go
negative. The approved limit is read from the **group parent**, so related
entities cannot stack lines.

---

## Post-install steps

Run in order after `bench migrate`.

1. **Create the Ops Manager user.** `muhammad@motleyterpz.com` is *not* a User on
   the site — the old flow only ever emailed the address. Ops Manager cannot
   approve until the User exists. Once created, re-run the phase 1 patch or set
   the field by hand:
   ```
   bench --site <site> execute cannabis_management.patches.install_credit_and_ar_phase1.execute
   ```

2. **Assign roles.** `Credit Finance`, `Managing Director`, `Ops Manager` and
   `Collections Officer` are created empty. At minimum give `Managing Director`
   to `imran@motleyterpz.com` and `Ops Manager` to the Ops user.

3. **Open Credit Policy Settings** and set:
   * `policy_effective_date` — **nothing runs until this is set.**
   * `chief_executive_officer` and `collections_officer`.
   * `finance_charge_income_account` if finance charges are to be enabled.
   * Review `terms_requiring_md_exception`; it is seeded with every non-COD
     template.

4. **Email Account for Credit Application threading.** Create an incoming Email
   Account so client, sales and finance correspondence lands on the credit file:
   * `Email Account Name`: e.g. `Credit Files`
   * `Enable Incoming`: on · `Default Incoming`: **off** unless this is the only
     inbound account on the site
   * `Append To`: `Credit Application`
   * `Append Emails to Sent Folder` / IMAP settings per your mail provider

   The DocType is already configured for it — `sender_field = email_id` and
   `subject_field = subject`, both on the **F · Correspondence** section. A reply
   from the AP contact threads onto the application as a `Communication`.

   To start a thread, use the form's ▸ **Email** action; `email_id` is
   pre-filled from the AP contact email on save.

5. **Decide on `Sales Master Manager`.** Customer already carried a permlevel-1
   DocPerm for the standard `Sales Master Manager` role, so anyone holding it can
   write `custom_credit_terms_template` — a gap against §1 ("Sales must not set
   terms"). The patch did not remove a standard ERPNext permission; either strip
   that role from permlevel 1 on Customer, or confirm nobody in Sales holds it.

6. **Verify the payment terms ladder.** `NET7`, `NET15`, `NET30`,
   `50% down NET15` and `50% down NET30` already existed and were left untouched;
   `COD`, `NET21`, `50% down NET7` and `50% down NET21` are created by the patch.

---

## Reproducibility

Custom fields are declared in `custom_fields.py` and applied idempotently by
`patches/install_credit_and_ar_phase1.py`, so `bench migrate` reproduces them on
any site. They are additionally carried by the app's existing unfiltered
`Custom Field` fixture. Roles and the payment terms ladder ship as filtered
fixtures in `hooks.py`.

The Module Def and the four roles are created in a **pre_model_sync** patch,
because `Credit Policy Settings` references those roles in its permissions and
would fail to sync otherwise.
