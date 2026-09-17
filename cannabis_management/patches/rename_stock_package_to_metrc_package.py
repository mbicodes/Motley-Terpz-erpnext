"""Deploy-time migration: bring a site still on the pre-rename schema up to
the current Metrc Package / Package Stock Movement design.

Run this ONCE on the target site, BEFORE `bench migrate`, whenever deploying
this app version to a site that still has the old DocTypes:

    bench --site <site> execute \
        cannabis_management.patches.rename_stock_package_to_metrc_package.execute

Then run `bench migrate` (picks up the renamed doctypes' new fields from the
current .json files) and restart the bench (`bench restart`, or the
supervisor/systemd equivalent) so worker processes drop their cached
controller modules for the old doctype names.

Safe to run on a site that has already been migrated (every step is a
no-op if its source DocType is already gone) and safe to re-run if it fails
partway through -- each rename is independent and idempotent.

Data-preserving: uses frappe.rename_doc, which does a real `RENAME TABLE`
and carries every existing row (and its own name/id) over untouched. This
is NOT a drop-and-recreate -- do not replace this with
frappe.delete_doc on a site that has real data.
"""

import frappe


def execute():
    frappe.flags.in_patch = True

    # Stock Package Consumption Entry -> Package Stock Movement. Renamed
    # before the parent below, as a matter of order (rename what something
    # depends on before the thing itself) -- frappe.rename_doc("DocType", ...)
    # updates every other DocField/Custom Field "options" pointing at the old
    # name (including the parent's own "consumption_log" Table field)
    # regardless of order, but this keeps the sequence easy to reason about.
    if frappe.db.exists("DocType", "Stock Package Consumption Entry"):
        frappe.rename_doc(
            "DocType", "Stock Package Consumption Entry", "Package Stock Movement", force=True
        )
    elif frappe.db.exists("DocType", "Metrc Package Consumption Entry"):
        # A site caught mid-way through this app's own internal history.
        frappe.rename_doc(
            "DocType", "Metrc Package Consumption Entry", "Package Stock Movement", force=True
        )

    # Stock Package -> Metrc Package.
    if frappe.db.exists("DocType", "Stock Package"):
        frappe.rename_doc("DocType", "Stock Package", "Metrc Package", force=True)

    frappe.db.commit()
