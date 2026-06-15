"""
Backward-compat shims for Frappe API changes.

Frappe removed get_linked_docs / get_dynamic_linked_docs from
frappe.model.delete_doc in ~v15.97.  Frappe CRM still imports them from there.
We add them back as module-level attributes on every bench migrate (via the
before_migrate hook) so CRM's after_migrate hook doesn't crash.
"""
import frappe


def install_frappe_shims():
    import frappe.model.delete_doc as _mod

    if hasattr(_mod, "get_linked_docs") and hasattr(_mod, "get_dynamic_linked_docs"):
        return

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
                SELECT parenttype AS reference_doctype, parent AS reference_docname
                FROM `tabDynamic Link`
                WHERE link_doctype = %s AND link_name = %s
            """, (doc.doctype, doc.name), as_dict=True)
            return [{"reference_doctype": r.reference_doctype,
                     "reference_docname": r.reference_docname} for r in rows]
        except Exception:
            return []

    _mod.get_linked_docs = get_linked_docs
    _mod.get_dynamic_linked_docs = get_dynamic_linked_docs
    frappe.logger().info("[cannabis_management.compat] Frappe delete_doc shims installed")
