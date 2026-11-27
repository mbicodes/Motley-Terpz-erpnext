"""
read_erp_page: list or read ERP pages for Frappe Assistant Core.

  Page       -> desk pages (e.g. AR Summary, Weekly Sales Order Report): record + source files (.js/.py/.html/.css)
  Workspace  -> sidebar workspaces: record with its content blocks parsed
  Web Page   -> website pages: record

Restricted to Administrator and System Manager, because it exposes page source code.
"""

import json
import os
from typing import Any, Dict

import frappe
from frappe import _

from frappe_assistant_core.core.base_tool import BaseTool

SOURCE_APP = "cannabis_management"
SOURCE_EXTENSIONS = {".js", ".py", ".html", ".css", ".scss", ".json", ".vue", ".md"}
MAX_FILE_CHARS = 150_000

LIST_FIELDS = {
    "Page": ["name", "title", "module", "standard", "modified"],
    "Workspace": ["name", "label", "module", "public", "modified"],
    "Web Page": ["name", "title", "route", "published", "modified"],
}


def _can_read() -> bool:
    return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def _to_plain(doc) -> Dict[str, Any]:
    # round-trip through frappe.as_json so datetimes/decimals serialise cleanly
    return json.loads(frappe.as_json(doc.as_dict()))


def _read_page_source(page) -> Dict[str, Any]:
    if page.standard != "Yes":
        return {"note": "Non-standard page: it has no source folder on disk."}

    try:
        module_path = os.path.realpath(frappe.get_module_path(page.module))
    except Exception as e:
        return {"error": f"Could not resolve module path for {page.module}: {e}"}

    folder = os.path.realpath(os.path.join(module_path, "page", frappe.scrub(page.name)))
    if not folder.startswith(module_path + os.sep) or not os.path.isdir(folder):
        return {"error": f"Source folder not found for page {page.name}", "expected_path": folder}

    files = {}
    for fname in sorted(os.listdir(folder)):
        fpath = os.path.join(folder, fname)
        if not os.path.isfile(fpath) or os.path.splitext(fname)[1].lower() not in SOURCE_EXTENSIONS:
            continue
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        files[fname] = {
            "content": text[:MAX_FILE_CHARS],
            "truncated": len(text) > MAX_FILE_CHARS,
            "size_chars": len(text),
        }

    return {"folder": folder, "files": files}


class ReadErpPage(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "read_erp_page"
        self.category = "Administration"
        self.source_app = SOURCE_APP
        self.description = (
            "List or read pages inside the ERP. Administrator / System Manager only.\n\n"
            "page_type 'Page' = desk pages (custom dashboards and report pages); reading one returns its record, "
            "allowed roles, and its source files (.js, .py, .html, .css) from the app. "
            "page_type 'Workspace' = sidebar workspaces (content blocks parsed). "
            "page_type 'Web Page' = website pages. "
            "Omit name to list pages (optionally filtered by module or a title search); give name to read one."
        )
        self.inputSchema = {
            "type": "object",
            "properties": {
                "page_type": {
                    "type": "string",
                    "enum": ["Page", "Workspace", "Web Page"],
                    "default": "Page",
                    "description": "Which kind of page to list or read.",
                },
                "name": {"type": "string", "description": "Page name to read. Omit to list pages."},
                "module": {"type": "string", "description": "When listing Page/Workspace, filter by module."},
                "search": {"type": "string", "description": "When listing, match against name/title (LIKE)."},
                "include_source": {
                    "type": "boolean",
                    "default": True,
                    "description": "For a desk Page, include its source files.",
                },
                "limit": {"type": "integer", "default": 50, "maximum": 500},
            },
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not _can_read():
            return {
                "success": False,
                "type": "permission",
                "error": _("read_erp_page requires the Administrator user or the System Manager role."),
            }

        page_type = arguments.get("page_type") or "Page"
        if page_type not in LIST_FIELDS:
            return {"success": False, "type": "validation", "error": _("Unsupported page_type {0}").format(page_type)}

        name = (arguments.get("name") or "").strip()
        try:
            if not name:
                return self._list(page_type, arguments)
            return self._read(page_type, name, bool(arguments.get("include_source", True)))
        except Exception as e:
            frappe.clear_messages()
            return {"success": False, "type": "read_failed", "error": str(e)}

    def _list(self, page_type: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        filters, or_filters = {}, None
        if arguments.get("module") and page_type in ("Page", "Workspace"):
            filters["module"] = arguments["module"]
        if arguments.get("search"):
            title_field = "label" if page_type == "Workspace" else "title"
            like = f"%{arguments['search']}%"
            or_filters = {"name": ["like", like], title_field: ["like", like]}

        rows = frappe.get_all(
            page_type,
            fields=LIST_FIELDS[page_type],
            filters=filters,
            or_filters=or_filters,
            order_by="modified desc",
            limit_page_length=min(int(arguments.get("limit") or 50), 500),
        )
        return {"success": True, "page_type": page_type, "count": len(rows), "pages": json.loads(frappe.as_json(rows))}

    def _read(self, page_type: str, name: str, include_source: bool) -> Dict[str, Any]:
        if not frappe.db.exists(page_type, name):
            return {"success": False, "type": "not_found", "error": _("{0} {1} not found.").format(page_type, name)}

        doc = frappe.get_doc(page_type, name)
        result: Dict[str, Any] = {"success": True, "page_type": page_type, "record": _to_plain(doc)}

        if page_type == "Page":
            result["allowed_roles"] = [r.role for r in (doc.get("roles") or [])]
            if include_source:
                result["source"] = _read_page_source(doc)
        elif page_type == "Workspace" and doc.get("content"):
            try:
                result["content_blocks"] = json.loads(doc.content)
            except Exception:
                pass

        return result


__all__ = ["ReadErpPage"]
