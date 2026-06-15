"""
Creates MTM Logistics workspace + 7 Custom HTML Blocks
cloned from Motley Logistics, filtered to Master Touch Manufacturing.
"""

import frappe


MTM_COMPANY = "Master Touch Manufacturing"

BLOCK_MAP = [
    # (source_name, new_name)
    ("Pending Orders Dashboard",     "MTM - Pending Orders Dashboard"),
    ("Orders Need to Schedule",      "MTM - Orders Need to Schedule"),
    ("Orders @ Lab",                 "MTM - Orders @ Lab"),
    ("Orders Preparing",             "MTM - Orders Preparing"),
    ("Order Prepared",               "MTM - Order Prepared"),
    ("Order Staged",                 "MTM - Order Staged"),
    ("Orders - Ready for Close Out", "MTM - Orders - Ready for Close Out"),
]


def _patch_js(script: str, is_first_block: bool) -> str:
    """Replace Motley-specific JS tokens with MTM equivalents."""
    if not script:
        return script

    # ── variable / event names ──────────────────────────────────────────────
    script = script.replace("_motleyWorkspaceCompany", "_mtmWorkspaceCompany")
    script = script.replace("motleyWorkspaceCompanyChange", "mtmWorkspaceCompanyChange")
    script = script.replace("_motleyCompany", "_mtmCompany")

    # ── default company value ───────────────────────────────────────────────
    script = script.replace(
        "window._mtmWorkspaceCompany || 'Motley Terpz'",
        f"window._mtmWorkspaceCompany || '{MTM_COMPANY}'"
    )

    # ── first-block company selector: seed with MTM default ─────────────────
    if is_first_block:
        script = script.replace(
            "window._mtmWorkspaceCompany || 'Motley Terpz'",
            f"window._mtmWorkspaceCompany || '{MTM_COMPANY}'"
        )

    # ── blocks 4-6 were missing var declaration + event listener ────────────
    # Inject them right after rootEl declaration if _mtmCompany is used but not declared
    if "_mtmCompany" in script and "var _mtmCompany" not in script:
        inject = (
            f"    var _mtmCompany = window._mtmWorkspaceCompany || '{MTM_COMPANY}';\n"
            "    window.addEventListener('mtmWorkspaceCompanyChange', function(e) {\n"
            "        _mtmCompany = e.detail.company;\n"
            "        loadPage(1);\n"
            "    });\n"
        )
        # Insert after "var rootEl = root_element;"
        script = script.replace(
            "var rootEl      = root_element;",
            "var rootEl      = root_element;\n" + inject,
            1
        )

    return script


def execute():
    frappe.flags.ignore_permissions = True

    # ── 1. Create / update 7 MTM Custom HTML Blocks ─────────────────────────
    for idx, (src_name, new_name) in enumerate(BLOCK_MAP):
        if not frappe.db.exists("Custom HTML Block", src_name):
            print(f"  SKIP – source block not found: {src_name}")
            continue

        src = frappe.get_doc("Custom HTML Block", src_name)
        is_first = idx == 0

        if frappe.db.exists("Custom HTML Block", new_name):
            doc = frappe.get_doc("Custom HTML Block", new_name)
        else:
            doc = frappe.new_doc("Custom HTML Block")
            doc.name = new_name

        doc.html   = src.html   or ""
        doc.style  = src.style  or ""
        doc.script = _patch_js(src.script or "", is_first)

        # Copy roles if any
        doc.set("roles", [])
        for r in (src.roles or []):
            doc.append("roles", {"role": r.role})

        doc.save(ignore_permissions=True)
        print(f"  OK – {new_name}")

    # ── 2. Create / update MTM Logistics Workspace ───────────────────────────
    ws_name = "MTM Logistics"
    if frappe.db.exists("Workspace", ws_name):
        ws = frappe.get_doc("Workspace", ws_name)
    else:
        ws = frappe.new_doc("Workspace")

    ws.label           = ws_name
    ws.title           = ws_name
    ws.icon            = "fal fa-ambulance"
    ws.indicator_color = "green"
    ws.public          = 1

    # Content: same 7-block layout with MTM block names
    import json, re
    content_blocks = []
    for _, new_name in BLOCK_MAP:
        safe_id = re.sub(r'[^a-z0-9]', '_', new_name.lower())
        safe_id = re.sub(r'_+', '_', safe_id).strip('_')
        content_blocks.append({
            "id":   safe_id,
            "type": "custom_block",
            "data": {"custom_block_name": new_name, "col": 12}
        })
    ws.content = json.dumps(content_blocks)

    # No doctype links — custom HTML blocks handle all the UI
    ws.set("links", [])

    # Register each block in the Workspace Custom Block child table
    # (Frappe won't render blocks that aren't listed here)
    ws.set("custom_blocks", [])
    for _, new_name in BLOCK_MAP:
        ws.append("custom_blocks", {"custom_block_name": new_name})

    ws.save(ignore_permissions=True)
    print(f"  OK – Workspace: {ws_name}")

    frappe.db.commit()
    print("\nDone – MTM Logistics workspace created.")
