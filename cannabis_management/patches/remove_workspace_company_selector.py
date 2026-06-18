"""
Remove the dynamic workspace-company system from all Custom HTML Blocks.

Two mechanisms to strip:
1. Variable + event-listener pattern (blocks that LISTEN for company changes)
2. "Dynamic company selector" IIFE appended at end of script (blocks that OWN the selector)

After this patch every block uses a hardcoded company string; the Company
selector UI no longer appears and the cross-block event system is gone.
"""

import re
import frappe

REPLACEMENTS = [
    (
        "window._mtmWorkspaceCompany || 'Master Touch Manufacturing'",
        "'Master Touch Manufacturing'",
    ),
    (
        "window._motleyWorkspaceCompany || 'Motley Terpz'",
        "'Motley Terpz'",
    ),
    (
        "window._tsbcWorkspaceCompany || 'TSBC Ranch'",
        "'TSBC Ranch'",
    ),
]

LISTENER_RE = re.compile(
    r"window\.addEventListener\(['\"](?:mtm|motley|tsbc)WorkspaceCompanyChange['\"]"
    r".*?}\s*\);",
    re.DOTALL,
)

# The company selector IIFE block + outer closing — everything from the
# comment marker through the final })(); of the outer wrapper.
SELECTOR_MARKER = "// ── Dynamic company selector"


def _remove_selector_iife(script):
    """Cut from the selector marker to end of script, re-close the outer IIFE."""
    idx = script.find(SELECTOR_MARKER)
    if idx == -1:
        return script, False

    # Walk back to find the last newline before the marker (keep it tidy)
    cut = script.rfind("\n", 0, idx)
    if cut == -1:
        cut = idx

    # Everything before the cut + close the outer IIFE
    new_script = script[:cut].rstrip() + "\n})();"
    return new_script, True


def _clean_script(script):
    changed = False

    for old, new in REPLACEMENTS:
        if old in script:
            script = script.replace(old, new)
            changed = True

    cleaned, n = LISTENER_RE.subn("", script)
    if n:
        script = cleaned
        changed = True

    script, cut = _remove_selector_iife(script)
    if cut:
        changed = True

    return script, changed


def execute():
    blocks = frappe.db.sql(
        """SELECT name FROM `tabCustom HTML Block`
           WHERE script LIKE '%WorkspaceCompany%'
              OR script LIKE '%WorkspaceCompanyChange%'
              OR script LIKE '%Dynamic company selector%'""",
        as_dict=True,
    )

    if not blocks:
        print("  No blocks found — nothing to update.")
        return

    for b in blocks:
        doc = frappe.get_doc("Custom HTML Block", b.name)
        if not doc.script:
            continue

        new_script, changed = _clean_script(doc.script)
        if not changed:
            print(f"  SKIP {b.name} — no matching patterns")
            continue

        doc.script = new_script
        doc.save(ignore_permissions=True)
        print(f"  OK – {b.name}")

    frappe.db.commit()
    print("\nDone.")
