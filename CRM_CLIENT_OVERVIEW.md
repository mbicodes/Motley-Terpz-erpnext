# Motley Terpz & TSBC Ranch — CRM System Overview
### How Everything Is Managed

**Prepared by:** Wolfiz Solutions / AllTech Virtual  
**System:** ERPNext + Frappe CRM  
**Date:** May 2026

---

## What This System Does

Your CRM replaces the Google Sheet with a live, automated system that:

- Tracks every brand, buyer, distributor, and retailer across 4 business lines
- Shows real-time AR balances, aging, and payment history for every account
- Automatically blocks invoices for customers with overdue or high debt
- Sends Slack alerts for COD customers and blocked account attempts
- Emails weekly financial reports to Nikki, Matt, and Imran automatically
- Keeps all demand estimates, notes, flags, and ClickUp links in one place

---

## Part 1 — The 4 Pipelines

Each business line has its own Kanban view pinned in the CRM sidebar.

| Pipeline | Company | Who Manages |
|---|---|---|
| ❄️ Fresh Frozen | TSBC Ranch | Nikki / Matt |
| 🌿 Rosin / Solventless | Motley Terpz | Nikki / Matt |
| 🏪 Retail / Distro | Both | Nikki |
| ⚙️ Tolling | Motley Terpz | Matt only (restricted) |

**Tolling is private** — only users with the "CRM Tolling Access" role can see Tolling leads.

---

## Part 2 — Lead Stages (Kanban Columns)

Every account moves through 6 stages across the board. Drag the card or change the Status field.

| Stage | What it means |
|---|---|
| **Lead** | New — not yet contacted |
| **Contacted** | Reached out, waiting for response |
| **Sample / QC** | Sample sent or QC in progress |
| **Active** | Buying regularly |
| **Inactive** | Was active, gone quiet |
| **Lost** | Closed, not going forward |

---

## Part 3 — Account Information on Each Lead Card

Every account card has a **Motley Terpz** tab with five sections of data.

### A. Identity & Ownership

What the account is and who owns it.

| Field | Purpose |
|---|---|
| **Relationship Tier** *(required)* | AAA → AA → A → Friends & Family → WIP → Lead |
| **Pipeline** | Which of the 4 business lines |
| **Account Owner** | Nikki, Matt, or Jamie |
| **Company** | TSBC Ranch / Motley Terpz / Both |
| **Revenue Size (Est.)** | $25M+ / $5M+ / $1M+ / $500K+ / $100K+ / <$50K |

### B. Activity & Behavior

How active the account is and when to follow up.

| Field | Purpose |
|---|---|
| **Buyer Activity** | Consistent / Inconsistent / Deposit / Never Purchased / Collab / Have not contacted |
| **Last Contact Date** | When you last spoke to this account |
| **Next Follow-up Date** | When to reach out next |
| **Notes** | Free-text history, context, special instructions |

### C. Flags & Special Handling

Operational flags that trigger automated alerts.

| Field | Purpose |
|---|---|
| **COD Only** | Triggers Slack alert to Muhammad on every invoice |
| **Single Source** | Account buys exclusively from you |
| **No-OCAL** | Account does not use OCAL |
| **Account Flags** | Additional flags: Custom QC Process, Do Not Contact, etc. |
| **ClickUp Link** | Direct link to the account's ClickUp task |
| **Slack Channel** | Slack channel for this account |

### D. Monthly Demand (lbs)

Matt's pipeline view. Estimated monthly demand by product type.

Fresh Frozen · Rosin · VRR · Food Grade · Bubble Hash · CPG · BHO / Live Resin · THCA · Trim / Biomass · Flower / Pre-rolls · Other

### E. ERPNext Live Data *(read-only, auto-updated nightly)*

Financial data pulled from ERPNext every weeknight. No manual entry needed.

| Field | What it shows |
|---|---|
| AR Balance | Total unpaid invoice balance |
| AR Aging (days) | Days since oldest unpaid invoice was due |
| AR Status | Clean / Watch / Overdue / Blocked |
| COD Flag | Auto-set if Payment Terms say COD |
| Last Invoice Date / Amount | Most recent Sales Invoice |
| Last Payment Date | Most recent payment received |
| MTD Revenue | Revenue this calendar month |
| 8-Week Trailing Revenue | Rolling 8-week revenue |
| Payment Terms | From ERPNext Customer record |
| Last Synced | Timestamp of last nightly sync |

---

## Part 4 — Relationship Tiers

| Tier | Description |
|---|---|
| **AAA** | Top-tier — consistent, high-volume, most reliable |
| **AA** | Strong buyer, occasional variance |
| **A** | Regular but lower volume or frequency |
| **Friends & Family** | Personal relationship, special pricing |
| **WIP** | Currently being onboarded |
| **Lead** | Prospect — no transaction yet |

Tier is **required** on every lead. You cannot save without it.

---

## Part 5 — AR Status (Auto-Calculated Every Night)

| Status | Rule |
|---|---|
| ✅ **Clean** | AR balance = $0 |
| 👀 **Watch** | AR > $0, aging 1–30 days |
| ⚠️ **Overdue** | Oldest unpaid invoice 31–90 days past due |
| 🚫 **Blocked** | AR > $50,000 OR oldest invoice > 90 days past due |

The status updates automatically every weeknight. No manual action needed.

---

## Part 6 — AR Enforcement (Automatic)

### What happens when someone tries to submit an invoice or order for a Blocked customer

**Regular users** → Hard error. The document **cannot be submitted**. They must contact Finance first.

**Admin / System Manager** → Red warning shown. They can proceed but are warned.

**Either way** → Slack notification sent automatically to **Matt, Imran, and Nikki** with:
- Customer name
- Document type (Invoice or Order)
- Who tried to submit it
- Reason (balance exceeded / days overdue)

### How to unblock a customer

1. Record the payment in ERPNext (Payment Entry against the overdue invoices)
2. The nightly sync recalculates AR Status overnight
3. Block lifts automatically — no manual action needed beyond recording the payment

---

## Part 7 — COD Enforcement (Automatic)

### What triggers it

When a Sales Invoice is submitted for any customer marked **COD Only** — either via the checkbox or the Account Flags field.

### What happens

A **Slack alert** is sent immediately containing:
- Customer name
- Invoice number and amount
- Who submitted the invoice
- Reminder to confirm cash was collected

### How to mark a customer as COD Only

Open the CRM Lead → **Motley Terpz** tab → **Flags & Special Handling** → check **COD Only**.

The nightly sync also sets the COD flag automatically if the customer's ERPNext Payment Terms contain "COD".

---

## Part 8 — Automated Reports

### Nikki's Weekly AR Report

**When:** Every Monday at 8:00 AM UTC  
**Sent to:** nikki@motleyterpz.com  
**CC:** matt@motleyterpz.com, imran@motleyterpz.com

Shows one row per customer with outstanding AR, including:

| Column | Details |
|---|---|
| Account | Customer name |
| Company | TSBC Ranch / Motley Terpz / Both |
| Tier | AAA / AA / A / etc. |
| Rev. Size | Estimated revenue ($5M+, etc.) |
| Outstanding AR | Total unpaid balance |
| Oldest Due Date | Highlighted red if overdue |
| Last Payment | Date of last payment received |
| New Orders | Orders placed this week |
| COD | Flag if COD Only |

Rows with overdue invoices or COD flags are highlighted amber.

### Matt's Weekly Sales Report

**When:** Every Friday  
**Sent to:** Matt, Nikki, Jamie, Imran, Muhammad, Osama

Contains (as PDF attachment):
- Sales Orders placed this week
- Sales Invoices issued this week
- Delivery Notes this week
- AR gathered this week
- AR collected this week
- Legacy AR collected

---

## Part 9 — Nightly Sync

Every weeknight (Mon–Fri), the system automatically:

1. Finds all CRM Leads with a linked ERPNext Customer
2. Pulls live financial data from ERPNext for each customer
3. Writes the data back to the CRM Lead's read-only fields
4. Recalculates AR Status using the threshold rules
5. Sets COD Flag based on Payment Terms

**Nothing needs to be done manually.** The sync runs in the background.

To trigger a manual sync from the ERPNext console:
```python
from cannabis_management.api.crm_sync import sync_now
sync_now()            # syncs all leads
sync_now("LEAD-001")  # syncs one specific lead
```

---

## Part 10 — Tolling Access Control

The Tolling pipeline is completely hidden from users who do not have the **"CRM Tolling Access"** role. They cannot see Tolling leads in any view, search, list, or report.

### How to grant access

1. ERPNext → **Settings → User** → open the user's record
2. **Roles** table → add **CRM Tolling Access**
3. Save — takes effect immediately

---

## Part 11 — Step-by-Step: Key Operations

### Add a new lead

1. Open **Frappe CRM** in the sidebar
2. Click the correct pipeline (Fresh Frozen / Rosin / Retail-Distro / Tolling)
3. Click **New Lead** (top right)
4. Fill in:
   - Lead name (company / brand name)
   - **Motley Terpz** tab → set **Relationship Tier** (required)
   - Set **Pipeline**, **Account Owner**, **Company**
   - Add **Buyer Activity**, **Notes**, demand fields as known
5. Save

### Move a lead to a new stage

- **Kanban:** Drag the card to the target column
- **Lead card:** Open the lead → change **Status** field at the top

### Link an existing ERPNext customer

1. Open the CRM Lead
2. **Motley Terpz** tab → **ERPNext — Live Data** section (scroll to bottom)
3. Set the **ERPNext Customer** field to the matching Customer record
4. Save — the nightly sync will populate all financial fields by next morning

### Mark a customer as COD Only

1. Open the CRM Lead
2. **Motley Terpz** tab → **Flags & Special Handling** section
3. Check **COD Only**
4. Save — enforcement is active immediately on the next invoice

### Check why an invoice submission was blocked

The error message will say the reason (balance exceeded $50,000 or invoice > 90 days overdue). A Slack notification is also sent to Matt, Imran, and Nikki with the details.

To see the AR detail: open the CRM Lead → **ERPNext — Live Data** → check **AR Balance** and **AR Aging (days)**.

### Trigger Nikki's AR report manually

```python
from cannabis_management.api.nikki_ar_report import send_now
send_now()
```

### Grant Tolling access to a user

1. ERPNext → **Settings → User** → open the user
2. **Roles** table → add **CRM Tolling Access**
3. Save

---

## Part 12 — What Is Automated vs. Manual

| Task | How it works |
|---|---|
| AR balances updated in CRM | **Automatic** — nightly sync Mon–Fri |
| AR Status (Clean/Watch/Overdue/Blocked) | **Automatic** — recalculated every night |
| COD Flag set from Payment Terms | **Automatic** — nightly sync |
| Blocked invoice prevention | **Automatic** — fires on Sales Invoice / Order submit |
| Slack alert for blocked submit | **Automatic** — fires on submit |
| Slack alert for COD invoice | **Automatic** — fires on Sales Invoice submit |
| Nikki's weekly AR report | **Automatic** — every Monday 8 AM UTC |
| Matt's weekly sales report | **Automatic** — every Friday |
| Moving leads between stages | **Manual** — drag card or change Status field |
| Filling demand / tier / owner fields | **Manual** — account owner fills these |
| Linking lead to ERPNext customer | **Manual** — one-time setup per lead |
| Granting Tolling access | **Manual** — admin adds role in User settings |

---

## Part 13 — Pending Items Before Full Go-Live

| # | Item | Type | Status |
|---|---|---|---|
| A | Assign CRM Tolling Access role to Matt | Manual | ⏳ Pending |
| B | Run `bench migrate` on live server (`erp.alltechvirtual.com`) | Server | ⏳ Pending |
| C | Link each CRM Lead to its ERPNext Customer | Data entry | ⏳ Pending |
| D | Import ~1,850 accounts from Google Sheet | Data migration | ⏳ Pending |
| E | Build Matt's Pipeline Health Dashboard | Development | 🔲 Not started |

Staging server (`stage.alltechvirtual.com`) has been fully migrated and all fields are live.

---

## Quick Reference — Field Names

| CRM Label | Field Name | Where |
|---|---|---|
| Relationship Tier | `custom_relationship_tier` | Section A |
| Pipeline | `custom_pipeline` | Section A |
| Account Owner | `custom_account_owner` | Section A |
| Company | `custom_company` | Section A |
| Revenue Size | `custom_revenue_size` | Section A |
| Buyer Activity | `custom_buyer_activity` | Section B |
| Last Contact Date | `custom_last_contact_date` | Section B |
| Next Follow-up Date | `custom_next_followup_date` | Section B |
| Notes | `custom_notes` | Section B |
| COD Only | `custom_cod_only` | Section C |
| Single Source | `custom_single_source` | Section C |
| No-OCAL | `custom_no_ocal` | Section C |
| Account Flags | `custom_account_flags` | Section C |
| ClickUp Link | `custom_clickup_link` | Section C |
| Slack Channel | `custom_slack_channel` | Section C |
| Demand — Fresh Frozen | `custom_demand_fresh_frozen` | Section D |
| Demand — Rosin | `custom_demand_rosin` | Section D |
| Demand — BHO / Live Resin | `custom_demand_bho` | Section D |
| Demand — THCA | `custom_demand_thca` | Section D |
| Demand — Trim / Biomass | `custom_demand_trim` | Section D |
| Demand — Flower / Pre-rolls | `custom_demand_flower` | Section D |
| ERPNext Customer | `custom_erp_customer` | Section E |
| AR Balance | `custom_ar_balance` | Section E |
| AR Status | `custom_ar_status` | Section E |
| COD Flag (auto) | `custom_cod_flag` | Section E |
| Last Payment Date | `custom_last_payment_date` | Section E |
| MTD Revenue | `custom_mtd_revenue` | Section E |

---

*For technical support contact Osama — osama.ahmad@alltechvirtual.com*  
*For day-to-day CRM questions contact Muhammad — mbi@alltechvirtual.com*
