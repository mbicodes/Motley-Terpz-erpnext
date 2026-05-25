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
- **Custom fields** on every lead card — tiers, demand estimates, flags, ClickUp link
- **Live AR data** pulled nightly from ERPNext — balance, aging, last invoice, last payment, MTD revenue
- **AR enforcement** — blocked customers cannot have invoices/orders submitted
- **COD enforcement** — Muhammad gets a Slack alert whenever a COD customer is invoiced
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

Open the lead card → **Motley Terpz** tab → **Account Info** section → set the **Pipeline** field.

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

All custom fields are on the **Motley Terpz** tab of the lead card.

### Account Info Section

| Field | Type | Description |
|---|---|---|
| **Relationship Tier** ⚠️ | Select (required) | AAA / AA / A / Friends & Family / WIP / Lead |
| **Pipeline** | Select | Fresh Frozen / Rosin / Retail-Distro / Tolling |
| **Account Owner** | Link → User | Nikki, Matt, or Jamie |
| **Buyer Activity** | Select | Consistent / Inconsistent / Deposit / Never Purchased |
| **COD Only** | Checkbox | If checked, customer can only pay cash on delivery |
| **No-OCAL** | Checkbox | Customer does not use OCAL |
| **Single Source** | Checkbox | Customer buys from us exclusively |
| **Special Flags / Notes** | Text | Free-text notes (allergies, restrictions, special handling) |
| **ClickUp Link** | URL | Direct link to this account's ClickUp task |
| **Last Contact Date** | Date | When you last spoke to this account |
| **Next Follow-up Date** | Date | When to follow up next |

### Monthly Demand Section (lbs)

Matt's most important metric. Fill in the estimated monthly demand per product type.

| Field | Product |
|---|---|
| Fresh Frozen | Fresh frozen biomass |
| Rosin | Rosin / live rosin |
| VRR | VRR product |
| Food Grade | Food-grade trim |
| Bubble Hash | Bubble / ice water hash |
| CPG | CPG products |
| BHO | BHO extracts |
| THCA | THCA flower |
| Trim | Trim |
| Flower | Flower |

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

The **ERPNext — Live Data** section (collapsible) at the bottom of the Motley Terpz tab shows real-time financial data pulled from ERPNext. **All fields are read-only** — they are updated automatically every night.

| Field | What it shows |
|---|---|
| **ERPNext Customer** | The linked Customer record in ERPNext |
| **AR Balance** | Total outstanding invoice balance |
| **AR Aging (days)** | How many days the oldest unpaid invoice is overdue |
| **AR Status** | Clean / Watch / Overdue / Blocked (see table below) |
| **Last Invoice Date** | Date of the most recent sales invoice |
| **Last Invoice Amount** | Amount of the most recent sales invoice |
| **Last Payment Date** | Date of the most recent payment received |
| **MTD Revenue** | Revenue this calendar month |
| **8-Week Trailing Revenue** | Total revenue over the past 8 weeks |
| **Payment Terms** | Customer's payment terms from ERPNext |
| **Last Synced** | Timestamp of last nightly sync |

### AR Status Values

| Status | Condition |
|---|---|
| ✅ **Clean** | AR balance = $0 |
| 👀 **Watch** | AR balance > $0, aging under 30 days |
| ⚠️ **Overdue** | Oldest unpaid invoice 30–60 days overdue |
| 🚫 **Blocked** | AR balance > **$50,000** OR oldest invoice > **60 days** overdue |

> To link a CRM lead to an ERPNext customer, fill in the **ERPNext Customer** field. The nightly sync picks it up automatically from that point on.

---

## 7. AR Enforcement — Blocked Customers

When someone tries to submit a **Sales Invoice** or **Sales Order** for a blocked customer, the system intervenes automatically.

### What "Blocked" means
A customer is blocked if **either** condition is true:
- Outstanding AR balance exceeds **$50,000**, OR
- The oldest unpaid invoice is more than **60 days** past due date

### What happens on submit

**Regular users (non-admin):**
> A hard error is thrown. The document **cannot be submitted**. The user must contact Finance to resolve the outstanding balance first.

**Admin / System Manager:**
> A red warning message appears. The admin **can proceed** but is warned. Use this only when Finance has confirmed it is safe to proceed.

**Both cases:**
> An automatic **Slack notification** is sent to Matt, Imran, and Nikki with the customer name, document type, submitted-by user, and the reason (balance / aging).

### How to unblock a customer
1. Collect outstanding payments in ERPNext (Payment Entry against the overdue invoices)
2. The nightly sync will update the AR Status to Clean/Watch/Overdue
3. The block is lifted automatically once the threshold conditions are no longer met

---

## 8. COD Enforcement

If a customer is marked **COD Only** in CRM and someone submits a **Sales Invoice** for them, Muhammad (mbi@alltechvirtual.com) receives an automatic **Slack alert** to verify that cash was collected before the invoice posts.

### How to mark a customer as COD Only
Open the CRM Lead → **Motley Terpz** tab → **Account Info** → check **COD Only**.

The sync ensures this flag is also visible in the ERPNext Live Data section as the Payment Terms field.

### What the Slack alert contains
- Customer name
- Invoice number and amount
- Who submitted the invoice
- A reminder: *"This customer is marked COD Only in CRM. Confirm cash was collected."*

---

## 9. Tolling Pipeline — Access Control

The **Tolling** pipeline is hidden from most users. Only users with the **"CRM Tolling Access"** role assigned in ERPNext can see Tolling leads.

### How to grant Tolling access
1. In ERPNext go to: **User** → open the user's record
2. In the **Roles** table, add the role **CRM Tolling Access**
3. Save the user

Users without this role will see Fresh Frozen, Rosin/Solventless, and Retail/Distro leads normally — Tolling leads are simply invisible to them in all views, searches, and reports.

> Currently Matt needs this role assigned. See [Pending Steps](#13-pending-steps).

---

## 10. Nikki's Weekly AR Report

Every **Monday at 8:00 AM UTC**, an email is automatically sent to:
- **To:** nikki@motleyterpz.com
- **CC:** matt@motleyterpz.com, imran@motleyterpz.com

### What the report contains

One row per customer with outstanding AR > $0:

| Column | Description |
|---|---|
| Account | Customer name |
| Tier | Relationship tier badge (AAA / AA / A / etc.) |
| Outstanding AR | Total unpaid invoice balance |
| Oldest Due Date | Earliest unpaid invoice due date (red if overdue) |
| Last Payment | Date of last payment received |
| New Orders | Count of new Sales Orders placed this week |
| COD | COD flag if the customer is COD Only |

Rows with overdue invoices or COD flags are highlighted in amber.

### How to trigger it manually
In ERPNext console or via a whitelisted API call:
```python
from cannabis_management.api.nikki_ar_report import send_now
send_now()
```

---

## 11. Nightly Sync — How It Works

Every night (Mon–Fri), a background job runs `crm_sync.sync_crm_ar_data()`. It:

1. Fetches all CRM Leads that have an **ERPNext Customer** linked
2. Queries live ERPNext data for each customer
3. Writes the results back to the CRM Lead's read-only fields

### What gets synced
- AR Balance, AR Aging Days, AR Status
- Last Invoice Date + Amount
- Last Payment Date
- MTD Revenue, 8-Week Trailing Revenue
- Payment Terms
- Last Synced timestamp

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

Both **Sales Brand** and **Sales- Frozen Manufactures** share the same column structure (headers are on row 8; rows 1–7 are the legend key).

| Col | Sheet Header | → CRM Lead Field | Notes |
|---|---|---|---|
| A | Relationship Status | `custom_relationship_tier` + `custom_account_owner` | Combined in one cell — needs parsing (see below) |
| B | Account | `lead_name` | Often contains description after a dash — clean to name only |
| C | Location | `city` | |
| D | Date new lead | `custom_last_contact_date` | Use as lead creation date on import |
| E | Status flags | `custom_single_source`, `custom_no_ocal` checkboxes | Contains text values: "Single Source", "No Ocal", "QC Process", "Custom" |
| G | Last contact | `custom_last_contact_date` | Overrides col D if present |
| H | Buyer activity | `custom_buyer_activity` | Values: consistent / inconsistent / deposit / have not purchased |
| J | Notes | `custom_special_flags_notes` | |
| K | What do you know | Append to `custom_special_flags_notes` | |
| L | FROZEN | `custom_demand_fresh_frozen` | Numbers in lbs; some rows have text ("8k a month") — set to null |
| M | ROSIN | `custom_demand_rosin` | |
| N | VRR | `custom_demand_vrr` | |
| O | FOOD GRD | `custom_demand_food_grade` | |
| P | BUBBLE | `custom_demand_bubble_hash` | |
| Q | EDIBLES | *(no CRM field — append to notes)* | |
| S | CPG | `custom_demand_cpg` | |
| T | BHO LIVE | `custom_demand_bho` | Sheet uses col 28 for BHO too — use whichever is populated |
| U | FLOWER | `custom_demand_flower` | |
| W | Point of Contact | Contact record name | |
| X | Phone Number | `mobile_no` | |
| Y | Email | `email_id` | |
| Z | Contact / Website | `website` | |
| col 28 | BHO | `custom_demand_bho` | |
| col 30 | TRIM | `custom_demand_trim` | |
| col 31 | THCA | `custom_demand_thca` | |
| col 33 | ClickUp Notes | `custom_clickup_link` | Contains ClickUp task URL or account label |
| col 34 | Revenue potential | Append to `custom_special_flags_notes` | Values like "$5M+", "$25M+", "$1M+", "$100K+" |
| col 35 | Product Types / tags | Append to `custom_special_flags_notes` | Values like "Top 100", "HASHBRAND", "Bho toll" |

**Sales Retailers** columns are simpler:

| Col | Sheet Header | → CRM Lead Field |
|---|---|---|
| A | Store name | `lead_name` |
| B | Owners | `custom_account_owner` |
| C | Location | `city` |
| D | Info | `custom_special_flags_notes` |
| E | # Locations | Append to notes |
| F | Confirmed | Stage → Active if confirmed |
| G | To Big? | Append to notes |

---

### Tier + Owner Parsing (Column A)

Column A combines tier and owner in one string. Parsing rules:

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
| have not purchased (+ active outreach in notes) | **Contacted** or **Sample/QC** |
| have not purchased (+ no recent notes) | **Lead** |
| No puchase in a year | **Inactive** |
| Not in business | **Lost** |

---

### Migration Blockers — Fix Before Import

| Issue | Affected rows | Fix |
|---|---|---|
| Demand cells contain text, not numbers ("8k a month", "YES", "A lot") | ~10–15% | Normalization script: if not numeric, set to null |
| Account name in col B contains description after a dash | Very common | Truncate at ` - ` or clean manually post-import |
| Duplicate accounts ("dup", "duplicate" in Notes column J) | ~20 rows | Skip any row where col J contains "dup" or "duplicate" |
| Col A non-standard values ("Click up", "Nikki", "Jake") | ~30 rows | Default to tier = WIP, derive owner from col A text |
| Some demand values show `#REF!` (broken Excel formula) | A few cells | Treat as null |
| No ERPNext Customer link exists in the sheet | All rows | Must be matched by name and linked manually after import |

---

### Fields in the Sheet With No CRM Equivalent

These have no dedicated field today. All should be appended to `custom_special_flags_notes` during import so the data is not lost:

- **EDIBLES demand** (col Q)
- **P-ROLLS (pre-rolls) demand** (col V)
- **Revenue potential** (col 34: "$5M+", "$25M+", etc.)
- **"Top 100" / "HASHBRAND"** tags (col 35)
- **"What do you know"** text (col K)
- **Last Purchase** (col I — no dedicated field; only `last_invoice_date` exists via ERPNext sync)

---

### What CRM Adds That the Sheet Never Had

| New capability | How it works |
|---|---|
| Live AR balance, aging, last payment date | Pulled nightly from ERPNext once ERPNext Customer is linked |
| AR Status (Clean / Watch / Overdue / Blocked) | Auto-calculated each night |
| Hard block on invoice submit for overdue customers | Enforced at Sales Invoice / Sales Order submit |
| COD Slack alert | Fires automatically when a COD-flagged customer is invoiced |
| Nikki's weekly AR report | Auto-emailed every Monday |

---

## 13. Pending Steps

These items need to be done manually before CRM is fully live:

### A. Assign Tolling Access to Matt
1. ERPNext → **Settings** → **User** → open Matt's user
2. Roles table → add **CRM Tolling Access**
3. Save

### B. Run `bench migrate` on live server
The following patches are committed and waiting:
- `setup_crm_fields` — creates all custom fields on CRM Lead
- `setup_crm_lead_statuses` — creates the 6 pipeline stages
- `setup_crm_pipelines` — creates the 4 Kanban pipeline views
- `remove_production_batch_group` — removes stale custom fields from Purchase Receipt etc.

```bash
bench --site erp.alltechvirtual.com migrate
```

### C. Link CRM Leads to ERPNext Customers
For the nightly sync and AR enforcement to work, each CRM Lead needs its **ERPNext Customer** field filled in. This maps the CRM contact to the ERPNext billing record.

Open each lead → **Motley Terpz** tab → **ERPNext — Live Data** section → set **ERPNext Customer**.

### D. Google Sheet Data Migration
~1,850 existing accounts from Matt's Google Sheet (`CRM Sales.xlsx`) need to be imported as CRM Leads across 3 tabs. See [Section 12](#12-google-sheet-migration--field-mapping) for the full column-to-field mapping and cleaning rules. Steps:
1. Run the normalization script to parse tier+owner from col A, clean account names, skip duplicates, coerce demand values to numbers
2. Generate one CSV per pipeline (Rosin, Fresh Frozen, Retail/Distro, Tolling)
3. Upload each CSV via Frappe Data Import Tool

### E. Matt's Pipeline Health Dashboard
Not yet built. Planned to show:
- Total pipeline value
- Active accounts by pipeline
- Total outstanding AR and AR > 30 days
- New leads this week
- Accounts with no contact in 30+ days

---

*This guide covers everything built in the May 2026 CRM implementation sprint. For questions contact Osama (osama.ahmad@alltechvirtual.com).*
