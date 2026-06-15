"""
Patch: add backward-compat shims for get_linked_docs / get_dynamic_linked_docs
to frappe.model.delete_doc.

These functions were removed in Frappe ~15.97 but Frappe CRM still imports them
from that module.  Adding them back as module-level attributes before the
after_migrate hook fires prevents the ImportError in crm.api.doc.

Runs every migrate (no idempotency guard needed — it's pure in-memory patching).
"""
import sys
import frappe


def execute():
    import frappe.model.delete_doc as _del_mod

    if hasattr(_del_mod, "get_linked_docs") and hasattr(_del_mod, "get_dynamic_linked_docs"):
        return  # already patched (shouldn't happen, but be safe)

    from frappe.desk.form.linked_with import (
        get_linked_docs as _new_get_linked_docs,
        get_linked_doctypes,
    )

    def get_linked_docs(doc):
        linkinfo = get_linked_doctypes(doc.doctype)
        result = _new_get_linked_docs(doc.doctype, doc.name, linkinfo) or {}
        out = []
        for ref_dt, records in result.items():
            for rec in (records or []):
                name = rec.get("name") if isinstance(rec, dict) else None
                if name:
                    out.append({"reference_doctype": ref_dt, "reference_docname": name})
        return out

    def get_dynamic_linked_docs(doc):
        try:
            rows = frappe.db.sql("""
                SELECT dl.parent AS doctype, dl.parent AS reference_doctype,
                       dl.name  AS reference_docname
                FROM `tabDynamic Link` dl
                WHERE dl.link_doctype = %s AND dl.link_name = %s
                  AND dl.parenttype NOT IN ('Contact', 'Address')
            """, (doc.doctype, doc.name), as_dict=True)
            return [{"reference_doctype": r.doctype, "reference_docname": r.reference_docname}
                    for r in rows]
        except Exception:
            return []

    _del_mod.get_linked_docs = get_linked_docs
    _del_mod.get_dynamic_linked_docs = get_dynamic_linked_docs

    # Also expose on sys.modules so `from frappe.model.delete_doc import …` resolves
    sys.modules["frappe.model.delete_doc"] = _del_mod

    frappe.logger().info("[patch_frappe_delete_doc_compat] shims installed")
