"""
Purchase Order override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Purchase Order"]["on_submit"]

Responsibilities:
- When a Purchase Order is submitted to an internal supplier that represents
  another ERPNext company (e.g. TSBC Ranch), automatically create the
  corresponding inter-company Sales Order in that company — saved as Draft
  so the receiving company can review before submitting.
- Idempotent: skips creation if an inter-company SO already exists for
  this PO.
"""

import frappe


def on_submit(doc, method=None):
    _create_intercompany_sales_order(doc)


def _create_intercompany_sales_order(po):
    """
    Use ERPNext's native make_inter_company_sales_order to create a
    corresponding SO in the supplier's company (e.g. TSBC Ranch).
    Only fires when:
        1. The supplier has is_internal_supplier = 1
        2. The supplier represents_company is a known ERPNext company
        3. No inter-company SO already exists for this PO
    """
    supplier_data = frappe.db.get_value(
        "Supplier", po.supplier,
        ["is_internal_supplier", "represents_company"],
        as_dict=True,
    )
    if not supplier_data or not supplier_data.is_internal_supplier:
        return
    target_company = supplier_data.represents_company
    if not target_company or not frappe.db.exists("Company", target_company):
        return

    # Check whether an inter-company SO already exists
    existing = frappe.db.get_value(
        "Sales Order",
        {"inter_company_order_reference": po.name, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        frappe.msgprint(
            f"Inter-company Sales Order {existing} already exists for this Purchase Order.",
            alert=True,
        )
        return

    try:
        from erpnext.buying.doctype.purchase_order.purchase_order import (
            make_inter_company_sales_order,
        )
        so_doc = make_inter_company_sales_order(po.name)
        so_doc.flags.ignore_permissions = True
        so_doc.save()
        frappe.msgprint(
            f"Inter-company Sales Order <b>{so_doc.name}</b> created in "
            f"{target_company} (Draft — please review and submit).",
            alert=True,
        )
    except Exception as e:
        # Non-fatal: log and continue so the PO submit doesn't roll back
        frappe.log_error(
            f"MTM: Failed to create inter-company SO for PO {po.name}: {e}",
            "Inter-Company SO Error",
        )
