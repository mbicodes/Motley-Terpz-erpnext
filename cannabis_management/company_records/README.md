# Company Records Module

Centralizes company documents that have no native home in ERPNext: reconciliations,
COAs, LOIs/product holds, contractor agreements, contracts, tolling agreements,
vendor data sheets, bank/financial statements, onboarding packets, and a catch-all
Company Record doctype.

## Entity-Level Access Scoping (manual setup)

Every doctype in this module carries a `business_entity` Link field pointing to the
**Business Entity** master. To restrict a user to one entity (e.g. a TSBC-only
bookkeeper who must never see Motley Terpz records):

1. Open **User Permission** (or the "User Permissions" section in the user's page).
2. Create a record: User = the user, Allow = `Business Entity`,
   For Value = the entity (e.g. `TSBC Ranch`).
3. Leave **"Apply to all document types"** checked.

Frappe then automatically filters every doctype whose `business_entity` field links
to Business Entity — no code or per-doctype configuration is needed.

## Roles (assign manually in the UI)

- **Accounting Team** — full control of Reconciliation Records and Bank/Financial
  Statement Records; read on most other records.
- **Operations** — full control of COAs, LOIs, and Onboarding Packets; create/read
  on Reconciliation Records; read/write on Vendor Data Sheets, Tolling Agreements
  and Company Records.
- **ERP Dev Team** — read-only on Reconciliation Records, COAs, and LOIs.
- **Director** — full control of everything in the module.

System Manager has full control of everything.

## Workflows

- **Reconciliation Approval** (Reconciliation Record): Draft -> Under Review
  (Accounting Team or Operations) -> Approved (Director) -> Locked (Director).
- **Contract Lifecycle** (Company Contract): Draft -> Active -> Expired/Terminated
  (Director only).

Both drive the doctype's own `status` field and are shipped as app fixtures.

## Design decisions

- The DocType is named **Company Contract** (labelled "Contract") because core
  ERPNext already ships a `Contract` doctype.
- Doctype names avoid "/" (LOI Product Hold Agreement, Bank Financial Statement
  Record) because slashes break folder names and URLs; UI labels keep the original
  wording where possible.
- Company Record tagging uses a `Record Tag` Table MultiSelect child pointing to a
  small **Company Record Tag** master rather than Frappe's built-in `_user_tags`:
  it gives a controlled vocabulary, works in standard filters and query reports,
  and migrates with the app. `_user_tags` is free-text and global to the site.
- All doctypes use human-readable naming series (REC-, COA-, LOI-, CNT-, CTR-,
  TOL-, VDS-, FIN-, ONB-, CRD- + year).
