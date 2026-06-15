# Motley Terpz & TSBC Ranch — Frappe CRM User Guide

**System:** ERPNext + Frappe CRM  
**Companies:** Motley Terpz · TSBC Ranch  
**Last Updated:** May 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [The 4 Pipelines](#2-the-4-pipelines)
3. [Lead Stages](#3-lead-stages)
4. [CRM Lead Card — Fields Reference](#4-crm-lead-card--fields-reference)
5. [Relationship Tiers](#5-relationship-tiers)
6. [ERPNext Live Data (Auto-Synced)](#6-erpnext-live-data-auto-synced)
7. [AR Enforcement — Blocked Customers](#7-ar-enforcement--blocked-customers)
8. [COD Enforcement](#8-cod-enforcement)
9. [Tolling Pipeline — Access Control](#9-tolling-pipeline--access-control)
10. [Nikki's Weekly AR Report](#10-nikkis-weekly-ar-report)
11. [Nightly Sync — How It Works](#11-nightly-sync--how-it-works)
12. [Google Sheet Migration — Field Mapping](#12-google-sheet-migration--field-mapping)
13. [Pending Steps](#13-pending-steps)

---

## 1. Overview

The Frappe CRM module replaces the Google Sheet that Matt used to track brands, buyers, and distributors. Every account from the sheet maps to a **CRM Lead** in Frappe. The key additions on top of standard Frappe CRM:

- **4 separate pipeline Kanban views** (one per business line)
- **Custom fields** on every lead card — tiers, demand estimates, flags, ClickUp link, company, revenue size
- **Live AR data** pulled nightly from ERPNext — balance, aging, last invoice, last payment, MTD revenue
- **AR enforcement** — blocked customers cannot have invoices/orders submitted
- **COD enforcement** — Slack alert fires whenever a COD customer is invoiced
- **Nikki's weekly AR report** — emailed every Monday morning

---

## 2. The 4 Pipelines

Each pipeline is a separate Kanban view in CRM. They appear pinned in the left sidebar.

| Pipeline | Company | Primary Owner |
|---|---|---|
| ❄️ **Fresh Frozen** | TSBC Ranch | Nikki / Matt |
| 🌿 **Rosin / Solventless** | Motley Terpz | Nikki / Matt |
| 🏪 **Retail / Distro** | Both | Nikki |
| ⚙️ **Tolling** | Motley Terpz | Matt only |

> **Tolling is restricted.** Only users with the **"CRM Tolling Access"** role can see Tolling leads. All other users see Fresh Frozen, Rosin/Solventless, and Retail/Distro only.

### How to assign a lead to a pipeline

Open the lead card → **Motley Terpz** tab → **Identity & Ownership** section → set the **Pipeline** field.

---

## 3. Lead Stages

Every pipeline uses the same 6 stages (columns on the Kanban board):

| Stage | Meaning |
|---|---|
| **Lead** | Initial contact — not yet reached |
| **Contacted** | Reached out, waiting for response |
| **Sample/QC** | Sample sent or quality check in progress |
| **Active** | Buying regularly |
| **Inactive** | Was active, gone quiet |
| **Lost** | Closed — not going forward |

To move a lead between stages: drag the card on the Kanban board, or open the card and change the **Status** field at the top.

---

## 4. CRM Lead Card — Fields Reference

All custom fields are on the **Motley Terpz** tab of the lead card, organized into five sections.

---

### Section A — Identity & Ownership

| Field | Type | Description |
|---|---|---|
| **Relationship Tier** ⚠️ | Select (required) | AAA / AA / A / Friends & Family / WIP / Lead |
| **Pipeline** | Select | Fresh Frozen / Rosin / Retail-Distro / Tolling |
| **Account Owner** | Link → User | Nikki, Matt, or Jamie |
| **Company** | Select | TSBC Ranch / Motley Terpz / Both |
| **Revenue Size (Est.)** | Select | $25M+ / $5M+ / $1M+ / $500K+ / $100K+ / <$50K / Unknown |

---

### Section B — Activity & Behavior

| Field | Type | Description |
|---|---|---|
| **Buyer Activity** | Select | Consistent / Inconsistent / Deposit / Never Purchased / Collab / Have not contacted |
| **Last Contact Date** | Date | When you last spoke to this account |
| **Next Follow-up Date** | Date | When to follow up next |
| **Notes** | Long Text | Free-text notes — context, history, special instructions |

---

### Section C — Flags & Special Handling

| Field | Type | Description |
|---|---|---|
| **Single Source** | Checkbox | Customer buys from us exclusively |
| **COD Only** | Checkbox | Customer can only pay cash on delivery — triggers Slack alert on invoice |
| **No-OCAL** | Checkbox | Customer does not use OCAL |
| **Account Flags** | Text | Comma-separated additional flags: No-OCAL, COD Only, Custom QC Process, Single Source, Do Not Contact |
| **ClickUp Link** | Data | Direct link to this account's ClickUp task |
| **Slack Channel** | Data | Slack channel for this account e.g. `#tsbc-accounts` |

> **COD enforcement** reads both the **COD Only** checkbox and the **Account Flags** field. Either is enough to trigger the alert.

---

### Section D — Monthly Demand (lbs)

Matt's most important metric. Fill in the estimated monthly demand per product type.

| Field | Unit | Product |
|---|---|---|
| Fresh Frozen | lbs/month | Fresh frozen biomass |
| Rosin | lbs/month | Rosin / live rosin |
| VRR | lbs/month | Vape-ready rosin |
| Food Grade | lbs/month | Food-grade trim |
| Bubble Hash | lbs/month | Bubble / ice water hash |
| CPG | units/month | Consumer packaged goods |
| BHO / Live Resin | lbs/month | BHO extracts / live resin |
| THCA | lbs/month | THCA flower |
| Trim / Biomass | lbs/month | Trim and biomass |
| Flower / Pre-rolls | lbs/month | Flower and pre-rolls |
| Other Demand Notes | Text | Free-text for non-standard products |

---

### Section E — ERPNext Live Data (read-only, auto-synced)

> All fields in this section are **read-only**. They update automatically every weeknight.

| Field | Description |
|---|---|
| **ERPNext Customer** | Linked Customer record in ERPNext — fill this to activate the sync |
| **AR Balance** | Total outstanding invoice balance |
| **AR Aging (days)** | Days since oldest unpaid invoice was due |
| **AR Status** | Clean / Watch / Overdue / Blocked |
| **COD Flag** | Auto-set from Payment Terms nightly |
| **Last Invoice Date** | Date of most recent Sales Invoice |
| **Last Invoice Amount** | Amount of most recent Sales Invoice |
| **Last Payment Date** | Date of most recent payment received |
| **MTD Revenue** | Revenue this calendar month |
| **8-Week Trailing Revenue** | Total revenue over the past 8 weeks |
| **Payment Terms** | Customer's payment terms from ERPNext |
| **Last Synced** | Timestamp of last nightly sync |

---

## 5. Relationship Tiers

| Tier | Description |
|---|---|
| **AAA** | Top-tier, highest volume, most reliable |
| **AA** | Strong account, consistent buyer |
| **A** | Good account, regular but smaller volume |
| **Friends & Family** | Personal relationship, special pricing |
| **WIP** | Work in progress — being onboarded |
| **Lead** | Prospect, no transaction yet |

> **Tier is required.** You cannot save a lead without setting this field.

---

## 6. ERPNext Live Data (Auto-Synced)

The **ERPNext — Live Data** section at the bottom of the Motley Terpz tab shows financial data pulled from ERPNext nightly. All fields are **read-only**.

### AR Status Values

| Status | Condition |
|---|---|
| ✅ **Clean** | AR balance = $0 |
| 👀 **Watch** | AR balance > $0, aging 1–30 days |
| ⚠️ **Overdue** | Oldest unpaid invoice **31–90 days** overdue |
| 🚫 **Blocked** | AR balance > **$50,000** OR oldest invoice > **90 days** overdue |

> To link a CRM lead to an ERPNext customer, fill in the **ERPNext Customer** field. The nightly sync picks it up automatically from that point on.

---

## 7. AR Enforcement — Blocked Customers

When someone tries to submit a **Sales Invoice** or **Sales Order** for a blocked customer, the system intervenes automatically.

### What "Blocked" means

A customer is blocked if **either** condition is true:
- Outstanding AR balance exceeds **$50,000**, OR
- The oldest unpaid invoice is more than **90 days** past due date

### What happens on submit

**Regular users (non-admin):**
> A hard error is thrown. The document **cannot be submitted**. The user must contact Finance to resolve the outstanding balance first.

**Admin / System Manager:**
> A red warning message appears. The admin **can proceed** but is warned. Use this only when Finance has confirmed it is safe to proceed.

**Both cases:**
> An automatic **Slack notification** is sent to Matt, Imran, and Nikki with the customer name, document type, submitted-by user, and the reason (balance / aging).

### How to unblock a customer
1. Record outstanding payments in ERPNext via **Payment Entry** against the overdue invoices
2. The nightly sync recalculates AR Status
3. The block lifts automatically once neither threshold condition is met

---

## 8. COD Enforcement

If a customer is flagged **COD Only** in CRM and someone submits a **Sales Invoice** for them, an automatic **Slack alert** is sent to verify that cash was collected before the invoice posts.

### How to mark a customer as COD Only

Two ways — either is enough to trigger enforcement:
1. Open the CRM Lead → **Motley Terpz** tab → **Flags & Special Handling** → check **COD Only**
2. Or add `COD Only` to the **Account Flags** text field (comma-separated)

The nightly sync also sets the **COD Flag** in the Live Data section automatically if the customer's ERPNext Payment Terms contain "COD".

### What the Slack alert contains
- Customer name
- Invoice number and amount
- Who submitted the invoice
- Reminder: *"This customer is marked COD Only in CRM. Confirm cash was collected."*

---

## 9. Tolling Pipeline — Access Control

The **Tolling** pipeline is hidden from most users. Only users with the **"CRM Tolling Access"** role assigned in ERPNext can see Tolling leads. Users without this role see zero Tolling leads in all views, searches, and reports.

### How to grant Tolling access
1. In ERPNext go to: **Settings → User** → open the user's record
2. In the **Roles** table, add the role **CRM Tolling Access**
3. Save — access takes effect immediately

---

## 10. Nikki's Weekly AR Report

Every **Monday at 8:00 AM UTC**, an email is automatically sent to:
- **To:** nikki@motleyterpz.com
- **CC:** matt@motleyterpz.com, imran@motleyterpz.com

### What the report contains

One row per customer with outstanding AR > $0. Rows with overdue invoices or COD flags are highlighted in amber.

| Column | Description |
|---|---|
| Account | Customer name |
| Company | TSBC Ranch / Motley Terpz / Both |
| Tier | Relationship tier badge (AAA / AA / A / etc.) |
| Rev. Size | Estimated revenue size ($5M+, etc.) |
| Outstanding AR | Total unpaid invoice balance |
| Oldest Due Date | Earliest unpaid invoice due date (red if overdue) |
| Last Payment | Date of last payment received |
| New Orders | Count of new Sales Orders placed this week |
| COD | COD flag if the customer is COD Only |

### How to trigger it manually
```python
from cannabis_management.api.nikki_ar_report import send_now
send_now()
```

---

## 11. Nightly Sync — How It Works

Every weeknight (Mon–Fri), a background job updates every CRM Lead that has an **ERPNext Customer** field filled in.

### What gets synced
- AR Balance, AR Aging Days, AR Status
- COD Flag (from Payment Terms)
- Last Invoice Date + Amount
- Last Payment Date
- MTD Revenue, 8-Week Trailing Revenue
- Payment Terms
- Last Synced timestamp

### AR Status thresholds (applied each night)

| Status | Rule |
|---|---|
| Clean | AR balance = $0 |
| Watch | AR > $0, aging ≤ 30 days |
| Overdue | Aging 31–90 days |
| Blocked | AR > $50,000 OR aging > 90 days |

### How to trigger a manual sync
```python
# Sync a single lead
from cannabis_management.api.crm_sync import sync_now
sync_now("LEAD-0001")

# Sync all linked leads
sync_now()
```

---

## 12. Google Sheet Migration — Field Mapping

Matt's original Google Sheet (`CRM Sales.xlsx`) has 4 tabs. Below is the complete map of every column to its CRM Lead field, what pipeline each tab feeds, and what needs cleaning before import.

### Sheet → Pipeline

| Sheet tab | # Accounts | → CRM Pipeline |
|---|---|---|
| Sales Brand | ~1,691 rows | Rosin / Solventless |
| Sales- Frozen Manufactures | ~127 rows | Fresh Frozen |
| Sales Retailers | ~33 rows | Retail / Distro |
| Sales Distro | Empty | — (Distro accounts appear in Sales Brand) |
| Any row in Brand/Frozen where TOLLING demand > 0 | Scattered | Tolling |

> **Total: ~1,850 accounts to import.**

---

### Column → CRM Lead Field

Both **Sales Brand** and **Sales- Frozen Manufactures** share the same column structure (headers on row 8; rows 1–7 are the legend key).

| Col | Sheet Header | → CRM Lead Field | Notes |
|---|---|---|---|
| A | Relationship Status | `custom_relationship_tier` + `custom_account_owner` | Combined in one cell — needs parsing (see below) |
| B | Account | `lead_name` | Often contains description after a dash — clean to name only |
| C | Location | `city` | |
| D | Date new lead | `custom_last_contact_date` | Use as lead creation date on import |
| E | Status flags | `custom_single_source`, `custom_no_ocal` checkboxes | Text values: "Single Source", "No Ocal", "QC Process", "Custom" |
| G | Last contact | `custom_last_contact_date` | Overrides col D if present |
| H | Buyer activity | `custom_buyer_activity` | consistent / inconsistent / deposit / have not purchased |
| J | Notes | `custom_notes` | |
| K | What do you know | Append to `custom_notes` | |
| L | FROZEN | `custom_demand_fresh_frozen` | Numbers in lbs; text values ("8k a month") → null |
| M | ROSIN | `custom_demand_rosin` | |
| N | VRR | `custom_demand_vrr` | |
| O | FOOD GRD | `custom_demand_food_grade` | |
| P | BUBBLE | `custom_demand_bubble` | |
| Q | EDIBLES | `custom_demand_other` (append) | No dedicated field |
| S | CPG | `custom_demand_cpg` | |
| T | BHO LIVE | `custom_demand_bho` | col 28 also has BHO — use whichever is populated |
| U | FLOWER | `custom_demand_flower` | |
| V | P-ROLLS | `custom_demand_other` (append) | No dedicated field |
| W | Point of Contact | Contact record name | |
| X | Phone Number | `mobile_no` | |
| Y | Email | `email_id` | |
| Z | Contact / Website | `website` | |
| col 28 | BHO | `custom_demand_bho` | |
| col 30 | TRIM | `custom_demand_trim` | |
| col 31 | THCA | `custom_demand_thca` | |
| col 33 | ClickUp Notes | `custom_clickup_link` | |
| col 34 | Revenue potential | `custom_revenue_size` | Map $25M+ / $5M+ / $1M+ / $500K+ / $100K+ / <$50K to Select options |
| col 35 | Product Types / tags | `custom_demand_other` (append) | "Top 100", "HASHBRAND", etc. |

**Sales Retailers** columns:

| Col | Sheet Header | → CRM Lead Field |
|---|---|---|
| A | Store name | `lead_name` |
| B | Owners | `custom_account_owner` |
| C | Location | `city` |
| D | Info | `custom_notes` |
| E | # Locations | Append to `custom_notes` |
| F | Confirmed | Stage → Active if confirmed |
| G | To Big? | Append to `custom_notes` |

---

### Tier + Owner Parsing (Column A)

| Col A value | → Tier | → Owner |
|---|---|---|
| `1 Nikki AAA` / `1 NIKKI AAA` | AAA | Nikki |
| `2 Nikki AA` | AA | Nikki |
| `3 Nikki A` / `3 NIKKI A` | A | Nikki |
| `4 NIKKI FRIENDS` / `4 Friends and family` | Friends & Family | Nikki |
| `5 Jake` | Lead | Jake |
| `6 Matt 1` / `A -Top Brand` / `A- Top brand` | AAA | Matt |
| `HOUSE AAA` | AAA | Internal / House |
| `Click up` | WIP | (derive from notes) |
| `Nikki` / `Jake` / `Jakes ` | WIP | Nikki / Jake |

---

### Buyer Activity → Lead Stage

| Sheet value (col H) | → CRM Stage |
|---|---|
| consistent | **Active** |
| inconsistent | **Inactive** |
| deposit | **Active** |
| have not purchased + active outreach in notes | **Contacted** or **Sample/QC** |
| have not purchased + no recent notes | **Lead** |
| No puchase in a year | **Inactive** |
| Not in business | **Lost** |

---

### Migration Blockers — Fix Before Import

| Issue | Affected rows | Fix |
|---|---|---|
| Demand cells contain text, not numbers ("8k a month", "YES", "A lot") | ~10–15% | Normalization script: if not numeric, set to null |
| Account name in col B contains description after a dash | Very common | Truncate at ` - ` or clean manually post-import |
| Duplicate accounts ("dup", "duplicate" in Notes column J) | ~20 rows | Skip rows where col J contains "dup" or "duplicate" |
| Col A non-standard values ("Click up", "Nikki", "Jake") | ~30 rows | Default to tier = WIP, derive owner from col A text |
| Demand values show `#REF!` (broken Excel formula) | A few cells | Treat as null |
| No ERPNext Customer link in the sheet | All rows | Must be matched by name and linked manually after import |

---

## 13. Pending Steps

### A. Assign Tolling Access to Matt
1. ERPNext → **Settings → User** → open Matt's user
2. Roles table → add **CRM Tolling Access**
3. Save

### B. Run `bench migrate` on live server
✅ **Staging (`stage.alltechvirtual.com`) — migrated May 2026**

Live server still needs migration:
```bash
bench --site erp.motleyterpz.io migrate
```

Patches that will apply:
- `setup_crm_fields` — all 36 custom fields across 5 sections
- `setup_crm_lead_statuses` — 6 pipeline stages
- `setup_crm_pipelines` — 4 Kanban pipeline views
- `remove_production_batch_group` — removes stale custom fields

### C. Link CRM Leads to ERPNext Customers
For the nightly sync and AR enforcement to work, each CRM Lead needs its **ERPNext Customer** field filled in.

Open each lead → **Motley Terpz** tab → **ERPNext — Live Data** section → set **ERPNext Customer**.

### D. Google Sheet Data Migration
~1,850 existing accounts from `CRM Sales.xlsx` need to be imported across 3 tabs. See [Section 12](#12-google-sheet-migration--field-mapping) for the full mapping. Steps:
1. Run normalization script — parse tier+owner from col A, clean account names, skip duplicates, coerce demand values to numbers, map revenue potential to Select options
2. Generate one CSV per pipeline (Rosin, Fresh Frozen, Retail/Distro, Tolling)
3. Upload each CSV via Frappe Data Import Tool

### E. Matt's Pipeline Health Dashboard
Not yet built. Planned to show:
- Total pipeline value by pipeline
- Active accounts per pipeline
- Total outstanding AR and AR > 30 days
- New leads this week
- Accounts with no contact in 30+ days

---

*CRM implementation sprint — May 2026. For questions contact Osama (osama.ahmad@alltechvirtual.com).*
