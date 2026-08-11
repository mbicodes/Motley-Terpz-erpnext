# Credit & AR — Manual Testing Runbook (Phases 1–3)

Everything below is done in the ERPNext UI on `stage.alltechvirtual.com`.
Budget about 45 minutes. Each step states **what you do** and **what must
happen** — if the "must happen" doesn't, that's a bug, note the step number.

The automated suite already covers all of this; this runbook is to see it with
your own eyes and to check the UI behaves, not just the server.

---

## 0. Setup (once, ~10 min)

> **Already done for you:** the five Customer records that are our own operating
> entities — `Motley Terpz`, `TSBC Ranch`, `Master Touch Manufacturing`, `MTPZ`
> and `LA Canna` — are flagged **Is Intercompany** and are excluded from every
> report and from the company metrics.

### 0.1 Create the Ops Manager user
`muhammad@motleyterpz.com` is **not** a User on the site — only an email address
the old code sent to. Until it exists, Ops cannot approve anything.

> **Users → New** · Email `muhammad@motleyterpz.com` · First Name `Muhammad` ·
> uncheck *Send Welcome Email* · Save.

### 0.2 Assign roles

| User | Roles to add |
|---|---|
| `imran@motleyterpz.com` | **Managing Director** |
| `muhammad@motleyterpz.com` | **Ops Manager** |
| whoever runs AR | **Credit Finance** |
| whoever chases money | **Collections Officer** |
| yourself (for testing) | **Credit Finance** (so you can create applications) |

> **User → open the user → Roles & Permissions tab → tick the role → Save.**

### 0.3 Fill in Credit Policy Settings

> **Search bar → "Credit Policy Settings"**

- **Policy Effective Date** — set it to **today**. Nothing scheduled runs until
  this is set, and everything dated before it becomes Legacy.
- **Managing Director** — should already be `imran@motleyterpz.com`.
- **Ops Manager** — set to `muhammad@motleyterpz.com` (now that the User exists).
- **Chief Executive Officer** / **Collections Officer** — set if you know them.
- Leave the thresholds at their defaults for testing.
- Save.

> ✅ **Must happen:** the orange banner at the top ("Policy Effective Date is not
> set…") disappears once you save with a date.

### 0.4 Create a test customer

> **Customer → New** · Name `TEST Buyer Co` · Group `Commercial` · Save.

> ✅ **Must happen:** on the **Credit Control** tab, *Credit Status* reads
> **COD**, *Approved Credit Limit* is 0, *Approved Payment Terms* is empty.

---

## 1. COD orders are unaffected (~3 min)

**Do:** Sales Order → New. Customer `TEST Buyer Co`, Company `Motley Terpz`,
add any item with a rate, delivery date next week. Leave **Mode of Payment** as
**Cash On Delivery**. Save.

> ✅ **Payment Terms Template** is set to **COD** automatically and the field is
> hidden (it only shows for Terms orders).
> ✅ **Credit Control** section: *Approval Status* = **Not Required**,
> *Print Blocked* unticked.
> ✅ **Submit** works immediately — no approval, no banner.
> ✅ **Print** and **Download PDF** both work.

---

## 2. Sample orders are forced to zero (~3 min)

**Do:** Sales Order → New. Same customer. Set **Sales Order Type = `Samples`**.
Add an item and deliberately **type a real rate** (e.g. 900). Save.

> ✅ The rate is reset to **0** and the Grand Total is **0.00**.
> ✅ *Approval Status* = **Not Required**, print not blocked.
> ✅ Submits normally. Stock still leaves inventory — a Delivery Note can be
> made from it as usual.

**Do:** on a new Sample order, also set Mode of Payment = `Payment Terms`.

> ✅ It is still treated as a Sample: zero value, no approval needed, no terms
> template. Sample beats payment mode.

---

## 3. Terms without a credit line — saves, but will not submit (~3 min)

**Do:** Sales Order → New. Same customer. Set **Mode of Payment = `Payment
Terms`**. Save.

> ✅ It **saves as a draft** — you can always write an order down.
> ✅ An orange message lists what will stop it: *"This order can be saved as a
> draft, but it cannot be submitted until… Terms not available — TEST Buyer Co
> has no approved credit line…"*
> ✅ Edit and re-save freely; the draft stays editable.

**Do:** now press **Submit**.

> ✅ **Must happen** — refused, listing every blocker at once:
> *"Terms not available — TEST Buyer Co has no approved credit line. The customer
> must complete the Line of Credit form and sign the Credit Agreement."*
> ✅ A **COD** order for the same customer still submits normally.

---

## 4. Grant a credit line (~10 min)

### 4.1 Create the application
> **Credit Application → New**

- Customer `TEST Buyer Co`, Type `New`. *(There is no Company field — the line
  is group-wide, so it is derived where needed.)*
- **Section A**: Exact Legal Buyer `TEST Buyer Co LLC`, Entity Type `LLC`,
  License Number `C11-TEST-0001`, License Expiry a future date, tick
  **License Verified**, Expected Weekly Volume `100`, Expected Monthly Revenue
  `100000`.
  *(Payment History Summary and Financial Capacity Notes are on the form but
  optional — leave them blank if you like.)*
- Save.

> ✅ *Verified By* and *Verified On* stamp themselves when you tick License
> Verified.
> ✅ *Group Existing Exposure* shows what this buyer already owes across all
> three companies.

### 4.2 The AP contact — required to hand the form in

The AP contact is demanded at **Submit for Review** (the applicant's own
submission), *not* at MD approval.

**Do:** with Section A filled but no AP contact, click **Submit for Review**.

> ✅ ❌ consolidated error: *"AP contact name is missing. AP contact direct line
> is missing. AP contact email is missing."*

Now test the format rules — **do these deliberately wrong first**

| Type this in | Expected |
|---|---|
| AP Contact Email = `ap@testbuyer.com` | ❌ rejected — *"a shared inbox, not an AP contact"* |
| AP Contact Email = `billing@testbuyer.com` | ❌ rejected, same |
| AP Contact Phone = `555-0100 ext 204` | ❌ rejected — *"looks like a mainline with an extension"* |
| AP Contact Phone = `x204` | ❌ rejected, same |
| AP Contact Email = `dana.reyes@testbuyer.com`, Phone = `(415) 555-0142` | ✅ saves |

### 4.3 Try to skip the process
**Do:** with only Section A filled, use the workflow button **Submit for
Review**, then **Recommend**.

> ✅ **Must happen** — one **consolidated** red error listing *every* missing
> item at once (recommended limit, recommended terms, etc.), not one at a time.

**Do:** set Recommended Limit `50000` and Recommended Terms `NET15`. Save. Try
**Recommend** again.

> ✅ Rejected once more — *"Enhanced assessment notes are required — the
> recommended limit exceeds $20,000.00."* (that's the enhanced review threshold
> doing its job).

**Do:** fill Enhanced Assessment Notes. Save. **Recommend**.

> ✅ State moves to **Pending MD Approval**.

### 4.4 Try to approve without the paperwork
**Do:** click **Approve**.

> ✅ **Must happen** — a consolidated error listing the four clauses, the
> onboarding form, and the approved limit/terms. The signed agreement is **not**
> on that list any more.

**Do:** tick **Finance Charge Clause**, **Collection Cost Clause**,
**Counsel-Approved Clause**, **Reconciliation Clause Acknowledged**,
**Onboarding Form Complete**. Set Approved Limit `50000` and Approved Terms
`NET15`. Save. **Approve**.

*(Leave the Credit Agreement unsigned and unattached — approval no longer waits
on it.)*

> ✅ **Must happen** — rejected: *"NET15 requires a written MD exception. Record
> the reason in Terms Exception Reason."* Per your decision, **every** non-COD
> term needs a written exception.

**Do:** fill Terms Exception Reason. Save. **Approve**.

> ✅ State = **Approved**, document submitted, *MD Approved* ticked,
> *Approved By* / *Approved On* stamped.
> ✅ *Effective From* = today, *Valid Until* = today + 90 days.

### 4.5 Approved, but not live yet

**Do:** open `TEST Buyer Co` → Credit Control tab.

> ✅ Credit Status is still **COD**, limit still 0, no terms template. Approval
> records the decision; it does not open the line.
> ✅ The owner, the AP contact and Finance are emailed *"Credit line approved,
> pending signed agreement"*.

**Do:** try a Terms Sales Order.

> ✅ Saves as a draft, but **will not submit**: *"Terms not available yet — the
> line for TEST Buyer Co is approved, but the signed Credit Agreement is not on
> file."*

**Do:** go back to the **submitted** Credit Application, tick **Credit Agreement
Signed**, attach any PDF as **Credit Agreement Document**, set the signed date,
and Save. *(These three stay editable after submit, by design.)*

> ✅ A comment appears: *"Signed Credit Agreement received — terms are now live
> for this customer."*

### 4.6 Check the customer
> **Open `TEST Buyer Co` → Credit Control tab**

> ✅ Credit Status = **Terms Approved** · Approved Credit Limit = **50,000** ·
> Approved Payment Terms = **NET15** · Terms Valid Until = today + 90 ·
> Active Credit Application links to the application · Reconciliation Clause
> Acknowledged ticked · AP contact and license copied across.
> ✅ On the main tab, **Payment Terms** = `NET15`.
> ✅ Under **Credit Limit**, a row for Motley Terpz with 50,000.

---

## 5. The Terms order round-trip (~8 min)

**Do:** Sales Order → New. `TEST Buyer Co`, Mode of Payment = **Payment Terms**,
Payment Terms Template = `NET15`, one item at 1,000 × 10 = 10,000. Save.

> ✅ Red banner: *"This Terms order is awaiting Managing Director approval. It
> cannot be submitted or printed until approved."*
> ✅ Credit Control section shows *Available Line* 50,000, *Credit Application*
> linked, *Print Blocked* ticked, Approval Status **Pending Approval**.
> ✅ The **Print** / **Email** / **Download PDF** menu entries are **gone**.

**Do:** try **Submit**.

> ✅ Blocked with the same message.

**Do — the important one:** the print block must hold even if you go around the
UI. Paste this in your browser address bar (replace the order name):

```
/api/method/frappe.utils.print_format.download_pdf?doctype=Sales%20Order&name=SAL-ORD-2026-XXXXX
```

> ✅ **Must happen** — a permission error, *not* a PDF. Client-side menu hiding
> is cosmetic; this is the real block.

**Do:** click **Request MD Approval**.

> ✅ A ToDo appears for `imran@motleyterpz.com` (and `muhammad@` once created),
> both get an email with the customer, amount, terms, exposure, available line
> and score, and a comment is added to the order.

**Do:** log in as a **Sales User** (not MD/Ops) and look at the order.

> ✅ **No** Approve/Reject buttons. And if they call the endpoint directly, the
> server refuses: *"Only the Managing Director or the Ops Manager can approve or
> reject Terms orders."*

**Do:** log in as `imran@motleyterpz.com` (or `muhammad@`), open the order,
click **Approve Terms**, add a note.

> ✅ Approval Status = **Approved**, *Terms Decided By/On* stamped, Print Blocked
> cleared, the ToDos close, and the order **creator** gets an email.
> ✅ Print and Download PDF now work.
> ✅ **Submit** now works.

### 5.1 Rejection
**Do:** create another Terms order, Request approval, then **Reject Terms** with
a reason.

> ✅ Status **Rejected**, reason stored and shown in the banner, the creator is
> emailed — and **print stays blocked**. A rejected Terms order must not leave
> the building.
> ✅ Submit still refused.

### 5.2 One term per account
**Do:** new Terms order for the same customer, but pick `NET30` instead of
`NET15`.

> ✅ Refused: *"TEST Buyer Co is approved for NET15, not NET30. One term per
> account. Changing the term needs a new Credit Application."*

---

## 6. Over the credit line (~7 min)

**Do:** new Terms order for 60,000 (the line is 50,000, and 10,000 is already
committed by the order from step 5).

> ✅ An orange message on save: *"This order puts $60,000.00 of credit against
> an available line of $40,000.00. A cleared deposit of $20,000.00 is required…"*
> ✅ *Required Deposit* = **20,000**.

**Do:** Request approval → Approve → **Submit**.

> ✅ **Must happen** — refused: *"A cleared deposit of $20,000.00 is required
> before this order can be submitted; $0.00 has cleared."* Approval alone is not
> enough. There is **no single-order exception at any amount**.

**Do:** Payment Entry → New · Type `Receive` · Party Type `Customer` · Party
`TEST Buyer Co` · Company `Motley Terpz` · Mode of Payment **`Cash`** ·
Paid Amount `20000`. In the **Credit & AR** section set **Ledger = `Deposit`**
and **Against Sales Order** = the order. Submit.

> ✅ Go back to the Sales Order and **Submit**. It now works.
> ✅ *Deposit Cleared Amount* = 20,000, *Deposit Cleared* ticked.

> **Note on "cleared":** cash counts immediately. A bank transfer or cheque only
> counts once **Clearance Date** is set (i.e. it appears on the bank
> reconciliation). A deposit that hasn't cleared is a promise, not a payment.

---

## 7. 50%-down terms (~3 min)

**Do:** revoke the current line (Credit Application → **Revoke**), then create
and approve a new application with Approved Terms = **`50% down NET30`** and a
limit of 200,000. Then raise a Terms order for 20,000.

> ✅ *Required Deposit* = **10,000** — the template's own up-front leg.
> ✅ Only the deferred 10,000 is charged against the available line, not the
> full 20,000.

---

## 8. Stop Work — holds (~10 min)

Holds are now raised automatically. The hold fields on Customer are read-only
because **AR Case owns them** — you never set them by hand.

### 8.1 Raise a hold from real data

**Do:** create a Sales Invoice for `TEST Buyer Co` and set its **Due Date to 6
days ago**, leaving it unpaid for any amount (even $50). Then ask me to run the
daily sweep, or wait for it (07:00 UTC).

> ✅ An **AR Case** appears, type **Hard Hold**, trigger *Past Due Days*.
> ✅ On the Customer: Credit Status **Hard Hold**, Hold Type **Hard Hold**, On
> Hold ticked, Active AR Case linked.
> ✅ Finance, the Collections Officer, the Ops Manager and the Sales owner are
> emailed.

**The three thresholds, if you want to see each:**

| Days past due | Amount | Result |
|---|---|---|
| 6 | $50 | **Hard Hold** — the age trigger |
| 2 | $1,000 | **Hard Hold** — the amount trigger |
| 2 | $500 | **Warning** only, work continues |

### 8.2 Gate 1 — what a hold stops

With the customer on Hard Hold, try each of these:

| Try | Expected |
|---|---|
| Submit a **COD** Sales Order | ❌ *"Stop Work. TEST Buyer Co is on Hard Hold…"* |
| Submit a **Terms** Sales Order | ❌ blocked |
| Submit a **Delivery Note** | ❌ blocked |
| Submit a **Work Order** for their Sales Order | ❌ blocked |
| Submit a production **Stock Entry** (Material Transfer for Manufacture / Manufacture) | ❌ blocked |
| Submit a **Sample** order | ✅ **allowed** — samples are exempt |
| Submit a **Quotation** | ✅ **allowed** — never gated |
| Submit a Material Receipt Stock Entry | ✅ allowed — not production |

> **Note:** a hold blocks **COD orders too**. That's the literal policy reading —
> no new work until cured. If you want COD trade to continue for held customers,
> tell me; it's a one-line change.

### 8.3 Release — try to get it wrong first

Open the AR Case. The **Release Hold** button only appears for Credit Finance.

| Try | Expected |
|---|---|
| Release as a Sales User | ❌ *"Only Credit Finance can release a hold."* |
| **Paid in Full** while still past due | ❌ *"…still shows $50.00 past due…"* |
| **Current on Approved Plan** with no plan | ❌ *"…has no active payment plan."* |
| **MD Exception** with the notes box empty | ❌ *"An MD exception must record the reason and who approved it."* |
| Edit **Status** to `Released` on the form directly | ❌ *"A hold is not released by editing this field. Use the Release Hold button…"* |
| **MD Exception** with notes | ✅ released, logged as an exception, MD + CEO + Finance emailed |

**Do:** now record a Payment Entry clearing the overdue invoice, then release
with **Paid in Full**.

> ✅ Releases. Customer back to COD/Terms Approved, On Hold cleared, Sales owner
> and Ops Manager emailed.
> ✅ Sales Orders submit again.
> ✅ **Run the daily sweep again** — the released case must **stay** Released.
> The scheduler never quietly reopens what a human closed.

### 8.4 Returned payments — the flag matters

**Do:** submit a Payment Entry against the customer, then cancel it **without**
ticking anything.

> ✅ Nothing happens. No hold. Ordinary corrections are not bounces.

**Do:** on another Payment Entry, tick **Returned / Bounced Payment** in the
Credit & AR section, add a reason, then cancel it.

> ✅ An **Immediate Hold** case appears, trigger *Returned Payment*, and the
> customer's *Returned Payments* counter goes up by one.

### 8.5 Broken promise to pay

**Do:** on an open AR Case set **Promise to Pay Date** to yesterday and an
amount, leaving the balance unpaid. Run the daily check.

> ✅ An **Immediate Hold** appears, trigger *Broken Promise to Pay*, the
> *Broken Promises* counter goes up, and the promise is cleared so it can't be
> counted twice.

### 8.6 Expired license

**Do:** set a customer's **License Expiry** to a past date while they hold terms.
Run the daily check.

> ✅ **Immediate Hold**, trigger *Expired License*. Finance is also warned at
> T-30 and T-7 before it expires.

### 8.7 Workout designation

**Do:** as a non-MD, create an AR Case with Case Type = `Workout`.

> ✅ ❌ *"Only the Managing Director can designate a workout account."*

**Do:** as the MD, do the same with a Workout Reason.

> ✅ Created, *Designated By/On* stamped, starting balance captured, paydown
> mode and percent defaulted from Credit Policy Settings (15%).

---

## 8b. Payment plans — two ledgers (~10 min)

**Do:** create an overdue invoice for `TEST Buyer Co` (due date in the past) and
a second invoice that is open but **not yet due**.

**Do:** as a **Sales User**, try to create an AR Case with Case Type =
`Payment Plan`.

> ✅ ❌ *"Only Credit Finance can put an account on a payment plan."*

**Do:** as Credit Finance, create the plan but leave the signed document off.

> ✅ ❌ consolidated error: signed document and signed date required.

**Do:** attach a document, set a principal, and add schedule rows that **don't**
add up to the principal.

> ✅ ❌ *"The schedule totals $800.00 but the plan principal is $1,000.00."*

**Do:** add a row dated in the past.

> ✅ ❌ *"Installment 1 is dated in the past."*

**Do:** fix it and save, then tick **MD Ratified** as the MD.

> ✅ Ratified By/On stamped.
> ✅ **The overdue invoice** now shows Ledger `Plan` with the AR Case linked.
> ✅ **The not-yet-due invoice** stays on Ledger `New Book`. The plan captures
> delinquent debt, not current trading.

### The netting rule
**Do:** create a Payment Entry, Ledger = **`New Book`**, and allocate it to the
plan invoice.

> ✅ ❌ *"Cross-ledger allocation… Plan money and new-book money are never
> netted. Split the receipt into one Payment Entry per ledger."*

**Do:** same receipt with Ledger = **`Plan`** against the same invoice.

> ✅ Saves and submits. Open the AR Case: the **first installment is marked Paid**
> with the amount and the Payment Entry recorded.
> ✅ Cancel that Payment Entry — the installment goes back to Pending.

**Do:** open a Payment Entry for this customer and look at the banner.

> ✅ Orange banner naming the plan, and **Allocate Payment Amount is switched
> off** — auto-allocation would spread one receipt across both books.

### Plan default
**Do:** make an installment overdue (or wait), then run the daily check.

> ✅ Installment → **Missed**, counter increments, an **Immediate Hold** case
> appears with trigger *Plan Default*, and Finance, the MD and Collections are
> emailed. All new work stops.
> ✅ Try a Terms order — refused, listing exactly what's missing: ratification,
> missed installments, or the absent separate credit line.

---

## 8c. Workout accounts (~8 min)

**Do:** as the MD, create an AR Case with Case Type = `Workout` and a reason.

> ✅ Starting balance captured, paydown mode and percent defaulted (15%),
> Customer Credit Status = **Workout**.

**Do:** try a **Terms** order for that customer.

> ✅ ❌ *"…is a workout account. Workout accounts are COD or prepaid only — zero
> new unsecured exposure, no exceptions."*

**Do:** create a **COD** order for $2,000.

> ✅ Orange message: a cleared paydown of **$300** (15%) is required.
> ✅ *Workout Paydown Required* = 300, AR Case linked.

**Do:** try to **Submit**.

> ✅ ❌ *"**No paydown, no product.** A cleared paydown of $300.00 is required…"*

**Do:** record a Payment Entry with Ledger = **`Workout Paydown`** against that
Sales Order for $300 (Mode of Payment `Cash` so it clears immediately). Submit
the order.

> ✅ Submits. *Workout Paydown Received* = 300.

### The balance only moves down
**Do:** raise a new invoice large enough to push the balance **above** the
starting balance, then run the workout review.

> ✅ The case goes **Defaulted**, a **Hard Hold** case opens automatically, the
> customer is on hold, and the MD and Finance are emailed *"Workout ended — the
> balance is rising"*.

---

## 9. Metrics, freeze and scoring (~10 min)

### 9.1 See the numbers
Ask me to run the metrics job, or wait for the daily run.

> ✅ **Credit Policy Settings → Live State** fills in: Current Total AR (new book
> only), Current DSO, Current CEI, Last Metrics Run.
> ✅ Legacy AR is reported separately and **never** triggers the freeze — at the
> time of writing that is ~$2.3M of legacy against the new book.

### 9.2 Freeze
**Do:** temporarily set **Total AR Cap** low enough to breach (e.g. `1000`) and
run the metrics job.

> ✅ **Company Freeze Active** ticks itself, with a reason naming every breached
> metric and the actual figures.
> ✅ MD, CEO, Finance and all Sales Managers are emailed.

**Do:** try a Terms order for a customer **in perfect standing with a live credit
line**.

> ✅ Refused: *"A company-wide credit freeze is in effect, so no account can add
> new exposure — good standing included."*

**Do:** try a COD order for the same customer.

> ✅ Allowed. The freeze stops new *unsecured* exposure, not all trade.

### 9.3 Unfreeze — nothing lifts silently
**Do:** with the cap still breached, try **Confirm Unfreeze**.

> ✅ ❌ *"The freeze cannot be lifted while a metric is still breached…"*, listing
> each one.

**Do:** try it with the notes box empty.

> ✅ ❌ *"Confirming an unfreeze must be in writing — record the basis."*

**Do:** restore the cap so nothing is breached, then Confirm Unfreeze with notes.

> ✅ Freeze clears, and a **Comment is written against Credit Policy Settings** —
> that's the exception register. Everyone is emailed.

> **Override path:** `unfreeze_override(reason)` needs the **CEO and the MD
> together**. The first person's call records a sign-off and raises a ToDo for
> the other; only the second signature lifts it, and the log says explicitly that
> the metrics were still breached. It refuses outright until **both** the MD and
> CEO are set in Credit Policy Settings — the CEO slot is currently blank.

### 9.4 Payment scores
Ask me to run the scoring job, or wait for the daily run.

> ✅ On Customer → **Payment Score** section: score, band, avg days to pay
> (signed — negative means they pay early), on-time %, weekly volume in grams
> and pounds.
> ✅ A customer paying ~3 days early with a perfect record scores around **734
> (Good)**; one paying ~20 days late scores around **453 (COD Only)**.
> ✅ A customer with **fewer than 3 paid invoices** shows band **Insufficient
> History**. The score field shows 0 because Frappe integers cannot be null —
> **the band is what counts**, and reports render it as "—".

---

## 9b. Finance charges (~5 min)

**Do:** in Credit Policy Settings tick **Finance Charges Enabled**, set Monthly
Rate `1.5`, set the **Finance Charge Income Account**, leave **Auto-Submit** off.
Ask me to run the monthly job.

> ✅ Customers whose approved Credit Application **lacks the counsel-approved
> clause** are skipped entirely — no charge is assessed under an agreement that
> doesn't carry the language.
> ✅ For those that qualify: one **Draft** Sales Invoice per customer, one line
> per past-due invoice, each line reading *"Finance charge on ACC-SINV-… — $X at
> 1.5%/month for N day(s)"*.

**Do:** set **Maximum Lawful Monthly Rate** to `1.0` and re-run.

> ✅ The **lower** rate wins — charges compute at 1.0%/month.

**Do:** run the job twice in a row.

> ✅ The second run creates **nothing**. Each source invoice carries *Finance
> Charge Applied Up To*, so the same days are never charged twice.

**Do:** check a **Legacy** invoice (posting date before the policy effective
date).

> ✅ Never charged, at any rate. §12 — legacy is collected on original terms.

---

## 9c. Reports and the workspace (~8 min)

**Do:** search for **"Credit and AR Control"** in the awesome bar and open the
workspace.

> ✅ Eight number cards across the top: new-book AR, cap headroom, DSO, CEI,
> accounts on hold, pending MD approvals, freeze status, legacy outstanding.
> ✅ Shortcuts to the four reports, and three work queues: applications pending
> MD, Terms orders awaiting approval, open AR cases.

**Do:** open each report in turn.

| Report | Look for |
|---|---|
| **Customer Credit Scorecard** | Score coloured by band; a customer with no score shows **—**, not 0. Negative "Avg Days to Pay" (pays early) shows green. Filter by band or credit status. |
| **Terms and Credit Line Register** | Days-to-Expiry coloured (red past due, orange ≤15). The **Agreement** column is a clickable attachment. A ✗ in *Counsel Clause* means no finance charges can be assessed on that account. |
| **Red List** | Status column colour-coded HOLD / PLAN / WORKOUT / PAST DUE. The header line carries the **Plan Book** totals — plan balance, due this week, received this week. |
| **Legacy Recovery Register** | Header states the legacy balance and that it does not count toward the cap. Every row's *Finance Charges* column reads **"Never — original terms"**. |

> **Note:** with `policy_effective_date` unset, the Legacy register is
> deliberately empty and says so — there is no Legacy/New Book split until you
> set the date.

**Do:** ask me to render the Friday report, or wait for Friday 08:00 UTC.

> ✅ One email with: freeze banner, metrics vs. thresholds (new book and legacy
> on **separate lines**), legacy recovered this week, new AR extended split
> good-standing vs. distressed, the AR/COD ratio of the week, and the Red List
> with Plan Book totals.

---

## 9d. Policy exemption (~5 min)

The escape hatch: one checkbox that takes an account out of the whole module.

**Do:** open a customer that is currently blocked (on hold, or with no credit
line). Go to **Credit Control → Policy Exemption**.

> **Note:** the checkbox and its reason are **permlevel 1** — you need
> `Credit Finance` or `Managing Director` to see or set them. Sales cannot grant
> an account an exemption from the credit policy.

**Do:** tick **Exempt from Credit & AR Policy** and try to save without a reason.

> ✅ ❌ Reason is mandatory.

**Do:** fill the reason and save.

> ✅ Blue banner at the top of the form: *"Exempt from the Credit & AR policy…"*
> ✅ Credit Status becomes **Policy Exempt**; *On Hold*, *Hold Type* and
> *Active AR Case* clear. (A hold badge that blocks nothing is worse than none.)
> ✅ A comment is written to the customer recording the exemption and the reason.

**Now try everything the policy would normally stop:**

| Try | Expected |
|---|---|
| A **Terms** Sales Order with **no credit line at all** | ✅ Saves — Approval Status `Not Required`, print **not** blocked |
| Submit that order | ✅ Submits, no MD approval needed |
| A Delivery Note / Work Order / production Stock Entry | ✅ Never blocked |
| Run the daily sweep | ✅ **No new AR Case** is raised, no matter how far past due |
| Run the scoring job | ✅ Not scored — score and band stay blank |
| Run finance charges | ✅ Never charged |
| A Payment Entry across two ledgers | ✅ Not enforced |

**But check the money is still counted:**

> ✅ The customer's outstanding balance still appears in **Total AR**, **DSO**
> and **CEI**, and they still show on the Red List and scorecard. Exempting the
> biggest debtor must not quietly switch off the freeze engine.

**Do:** untick the exemption and run the daily sweep again.

> ✅ The account goes straight back under the policy — the hold re-raises and
> Terms orders are refused again.

---

## 10. Things to look at, not test

- **Sales Order list view** now has *Mode of Payment* and *Approval Status* as
  standard filters — filter on `Pending Approval` to see the MD's queue.
- **Credit Application list** — filter by Status to see the pipeline.

---

## Known gaps at Phase 7

| Gap | Notes |
|---|---|
| `Sales Manager` can still edit Payment Terms Template | A pre-existing permlevel-1 DocPerm on Sales Order. §1 says Sales must not set terms. Tell me and I'll remove it. |
| `Sales Master Manager` can still edit Customer's approved terms | Same situation on Customer. |
| Ops Manager user still missing | `muhammad@motleyterpz.com` is not a User on the site; Ops cannot approve until it is created. |
| CEO routing slot blank | `unfreeze_override` refuses outright until both MD and CEO are set. |
| No automated test suite | Phase 8 was not built — stopped at Phase 7 by request. |

---

## Cleaning up

Delete in this order: Payment Entries (cancel first) → Sales Orders (cancel
first) → Credit Applications (cancel first) → the test Customer. Or ask me and
I'll run the cleanup.
