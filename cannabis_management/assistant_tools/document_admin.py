"""
Administrator-only document lifecycle tools for Frappe Assistant Core.

  admin_cancel_document            -> cancel a submitted document (optionally its linked submitted docs)
  admin_delete_submitted_document  -> delete a submitted/cancelled document (optionally cancelling first)

Both tools refuse to run unless the MCP session user is exactly "Administrator".
Every cancellation runs inside a savepoint, so a failure leaves nothing half-cancelled.
"""

from typing import Any, Dict, List, Tuple

import frappe
from frappe import _
from frappe.utils import strip_html

from frappe_assistant_core.core.base_tool import BaseTool

ADMIN_USER = "Administrator"
SOURCE_APP = "cannabis_management"


# --------------------------------------------------------------------------- helpers


def _admin_guard():
    if frappe.session.user != ADMIN_USER:
        return {
            "success": False,
            "type": "permission",
            "error": _("This tool is restricted to the Administrator user (current user: {0}).").format(
                frappe.session.user
            ),
        }
    return None


def _clean_error(exc: Exception) -> str:
    msg = strip_html(str(exc) or "").strip()
    if not msg and getattr(frappe.local, "message_log", None):
        try:
            last = frappe.local.message_log[-1]
            last = frappe.parse_json(last) if isinstance(last, str) else last
            msg = strip_html(last.get("message", "")).strip()
        except Exception:
            pass
    return msg or exc.__class__.__name__


def _new_savepoint(prefix: str) -> str:
    return f"{prefix}_{frappe.generate_hash(length=10)}"


def _validate_target(doctype: str, name: str):
    if not doctype or not name:
        return {"success": False, "type": "validation", "error": _("Both doctype and name are required.")}
    if not frappe.db.exists("DocType", doctype):
        return {"success": False, "type": "validation", "error": _("DocType {0} does not exist.").format(doctype)}
    if not frappe.db.exists(doctype, name):
        return {"success": False, "type": "not_found", "error": _("{0} {1} not found.").format(doctype, name)}
    return None


def _get_submitted_linked_docs(doctype: str, name: str) -> List[Dict[str, str]]:
    """Submitted documents that link to this one (same list the desk 'Cancel All' dialog shows)."""
    from frappe.desk.form.linked_with import get_submitted_linked_docs

    result = get_submitted_linked_docs(doctype, name)
    docs = result.get("docs", []) if isinstance(result, dict) else list(result or [])

    seen, out = set(), []
    for d in docs:
        key = (d.get("doctype"), d.get("name"))
        if key[0] and key[1] and key not in seen and key != (doctype, name):
            seen.add(key)
            out.append({"doctype": key[0], "name": key[1]})
    return out


class LinkedDocumentsError(Exception):
    def __init__(self, linked: List[Dict[str, str]]):
        super().__init__("Submitted documents are linked to this record.")
        self.linked = linked


def _cancel_many(docs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Cancel documents in repeated passes so dependency order sorts itself out.
    Each attempt has its own savepoint; raises if any document can never be cancelled.
    """
    pending: List[Tuple[str, str]] = [(d["doctype"], d["name"]) for d in docs]
    cancelled: List[Dict[str, str]] = []
    errors: Dict[str, str] = {}

    while pending:
        progress, still_pending = False, []
        for dt, dn in pending:
            sp = _new_savepoint("fac_cl")
            frappe.db.savepoint(sp)
            try:
                d = frappe.get_doc(dt, dn)
                if d.docstatus == 1:
                    d.cancel()
                cancelled.append({"doctype": dt, "name": dn})
                errors.pop(f"{dt} {dn}", None)
                progress = True
            except Exception as e:
                frappe.db.rollback(save_point=sp)
                frappe.clear_messages()
                errors[f"{dt} {dn}"] = _clean_error(e)
                still_pending.append((dt, dn))
        if not progress:
            detail = "; ".join(f"{k}: {v}" for k, v in errors.items())
            raise frappe.ValidationError(_("Could not cancel linked documents. {0}").format(detail))
        pending = still_pending

    return cancelled


def _cancel_document(doctype: str, name: str, cancel_linked: bool) -> List[Dict[str, str]]:
    """Cancel one submitted document. Returns linked documents that were cancelled with it."""
    linked = _get_submitted_linked_docs(doctype, name)
    if linked and not cancel_linked:
        raise LinkedDocumentsError(linked)

    cancelled_linked = _cancel_many(linked) if linked else []
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus == 1:
        doc.cancel()
    return cancelled_linked


def _linked_error(doctype: str, name: str, linked: List[Dict[str, str]]):
    return {
        "success": False,
        "type": "linked_documents",
        "error": _(
            "{0} {1} has {2} submitted document(s) linked to it. "
            "Call again with cancel_linked_documents=true to cancel them too."
        ).format(doctype, name, len(linked)),
        "linked_documents": linked,
    }


# --------------------------------------------------------------------------- tools


class AdminCancelDocument(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "admin_cancel_document"
        self.category = "Administration"
        self.source_app = SOURCE_APP
        self.description = (
            "Cancel a SUBMITTED Frappe/ERPNext document (docstatus 1 -> 2). Administrator user only.\n\n"
            "If other submitted documents link to it, the call fails and lists them, unless "
            "cancel_linked_documents=true, in which case they are cancelled first (like the desk 'Cancel All' button). "
            "Use dry_run=true to see the document's state and its linked submitted documents without changing anything. "
            "All-or-nothing: if any cancellation fails, every change made by the call is rolled back. "
            "Always confirm with the user before cancelling, and always run a dry_run first when "
            "cancel_linked_documents would be used."
        )
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType, e.g. 'Sales Invoice'"},
                "name": {"type": "string", "description": "Document name, e.g. 'ACC-SINV-2026-00012'"},
                "cancel_linked_documents": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also cancel submitted documents that link to this one.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Report state and linked submitted documents only; change nothing.",
                },
            },
            "required": ["doctype", "name"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        denied = _admin_guard()
        if denied:
            return denied

        doctype = (arguments.get("doctype") or "").strip()
        name = (arguments.get("name") or "").strip()
        cancel_linked = bool(arguments.get("cancel_linked_documents"))
        dry_run = bool(arguments.get("dry_run"))

        invalid = _validate_target(doctype, name)
        if invalid:
            return invalid
        if not frappe.get_meta(doctype).is_submittable:
            return {"success": False, "type": "validation", "error": _("{0} is not a submittable DocType.").format(doctype)}

        docstatus = frappe.db.get_value(doctype, name, "docstatus")
        if docstatus == 2:
            return {"success": True, "message": _("{0} {1} is already cancelled.").format(doctype, name)}
        if docstatus == 0:
            return {
                "success": False,
                "type": "validation",
                "error": _("{0} {1} is a draft; drafts can't be cancelled (delete it instead).").format(doctype, name),
            }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "doctype": doctype,
                "name": name,
                "docstatus": docstatus,
                "linked_submitted_documents": _get_submitted_linked_docs(doctype, name),
            }

        sp = _new_savepoint("fac_cancel")
        frappe.db.savepoint(sp)
        try:
            cancelled_linked = _cancel_document(doctype, name, cancel_linked)
            frappe.db.commit()
        except LinkedDocumentsError as e:
            frappe.db.rollback(save_point=sp)
            frappe.clear_messages()
            return _linked_error(doctype, name, e.linked)
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            frappe.clear_messages()
            return {"success": False, "type": "cancel_failed", "error": _clean_error(e)}

        return {
            "success": True,
            "message": _("{0} {1} cancelled.").format(doctype, name),
            "cancelled_linked_documents": cancelled_linked,
        }


class AdminDeleteSubmittedDocument(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "admin_delete_submitted_document"
        self.category = "Administration"
        self.source_app = SOURCE_APP
        self.description = (
            "Delete a submitted or cancelled Frappe/ERPNext document. Administrator user only.\n\n"
            "Cancelled (docstatus 2) and draft documents are deleted directly. A SUBMITTED document "
            "(docstatus 1) is only deleted when cancel_first=true: it is cancelled, then deleted. "
            "cancel_linked_documents=true also cancels submitted documents linking to it (they are cancelled, not deleted). "
            "force=true skips Frappe's link check on deletion; use only when explicitly asked. "
            "Deletion is permanent: always confirm the exact document with the user first."
        )
        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType, e.g. 'Sales Invoice'"},
                "name": {"type": "string", "description": "Document name"},
                "cancel_first": {
                    "type": "boolean",
                    "default": False,
                    "description": "If the document is submitted, cancel it before deleting.",
                },
                "cancel_linked_documents": {
                    "type": "boolean",
                    "default": False,
                    "description": "When cancelling first, also cancel submitted documents that link to it.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Delete even if other documents still link to it (frappe.delete_doc force).",
                },
            },
            "required": ["doctype", "name"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        denied = _admin_guard()
        if denied:
            return denied

        doctype = (arguments.get("doctype") or "").strip()
        name = (arguments.get("name") or "").strip()
        cancel_first = bool(arguments.get("cancel_first"))
        cancel_linked = bool(arguments.get("cancel_linked_documents"))
        force = bool(arguments.get("force"))

        invalid = _validate_target(doctype, name)
        if invalid:
            return invalid

        docstatus = frappe.db.get_value(doctype, name, "docstatus") or 0
        if docstatus == 1 and not cancel_first:
            return {
                "success": False,
                "type": "validation",
                "error": _(
                    "{0} {1} is submitted. Call again with cancel_first=true to cancel and then delete it."
                ).format(doctype, name),
            }

        sp = _new_savepoint("fac_delete")
        frappe.db.savepoint(sp)
        cancelled_linked: List[Dict[str, str]] = []
        try:
            if docstatus == 1:
                cancelled_linked = _cancel_document(doctype, name, cancel_linked)
            frappe.delete_doc(doctype, name, force=force)
            frappe.db.commit()
        except LinkedDocumentsError as e:
            frappe.db.rollback(save_point=sp)
            frappe.clear_messages()
            return _linked_error(doctype, name, e.linked)
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            frappe.clear_messages()
            return {"success": False, "type": "delete_failed", "error": _clean_error(e)}

        return {
            "success": True,
            "message": _("{0} {1} deleted.").format(doctype, name),
            "was_cancelled_first": docstatus == 1,
            "cancelled_linked_documents": cancelled_linked,
        }


__all__ = ["AdminCancelDocument", "AdminDeleteSubmittedDocument"]
