import json

import frappe

from cannabis_management.api.home_hub import is_custom

WORKSPACE = "Home"
LEGACY_BLOCK = "Home Hub"

SEED_LIMITS = {"workspace": 100, "dashboard": 100, "page": 100, "report": 200}

COLOURS = {
    "workspace": "Purple",
    "dashboard": "Cyan",
    "page": "Blue",
    "report": "Orange",
}


def install_home_hub():
    _rebuild_home_workspace()
    _drop_legacy_block()


def _seed_shortcuts() -> list[dict]:
    shortcuts: list[dict] = []
    seen: set[str] = set()

    def add(label, type_, link_to=None, url=None, colour=None):
        label = (label or "").strip()
        if not label or label.lower() in seen:
            return
        seen.add(label.lower())
        row = {"type": type_, "label": label, "color": colour}
        if url:
            row["url"] = url
        else:
            row["link_to"] = link_to
        shortcuts.append(row)

    rows = frappe.get_all(
        "Workspace",
        filters={"public": 1, "is_hidden": 0},
        fields=["name", "title", "module"],
        order_by="sequence_id asc, title asc",
        ignore_permissions=True,
    )
    count = 0
    for row in rows:
        if row.name == WORKSPACE or row.name == "Welcome Workspace":
            continue
        if not is_custom(row.module):
            continue
        if count >= SEED_LIMITS["workspace"]:
            break
        slug = frappe.scrub(row.title or row.name).replace("_", "-")
        add(row.title or row.name, "URL", url=f"/app/{slug}", colour=COLOURS["workspace"])
        count += 1

    count = 0
    for row in frappe.get_all(
        "Dashboard", fields=["name", "dashboard_name", "module"], ignore_permissions=True
    ):
        if not is_custom(row.module) or count >= SEED_LIMITS["dashboard"]:
            continue
        add(row.dashboard_name or row.name, "Dashboard", link_to=row.name,
            colour=COLOURS["dashboard"])
        count += 1

    count = 0
    for row in frappe.get_all(
        "Page", fields=["name", "title", "module"], order_by="title asc",
        ignore_permissions=True
    ):
        if not is_custom(row.module) or count >= SEED_LIMITS["page"]:
            continue
        add(row.title or row.name, "Page", link_to=row.name, colour=COLOURS["page"])
        count += 1

    count = 0
    for row in frappe.get_all(
        "Report",
        filters={"disabled": 0},
        fields=["name", "report_name", "module", "ref_doctype"],
        order_by="report_name asc",
        ignore_permissions=True,
    ):
        if not is_custom(row.module) or count >= SEED_LIMITS["report"]:
            continue
        add(row.report_name or row.name, "Report", link_to=row.name,
            colour=COLOURS["report"])
        count += 1

    return shortcuts

SECTIONS = [
    ("workspace", "Workspaces", lambda row: row["type"] == "URL"),
    ("dashboard", "Dashboards", lambda row: row["type"] == "Dashboard"),
    ("page", "Pages", lambda row: row["type"] == "Page"),
    ("report", "Reports", lambda row: row["type"] == "Report"),
]

SECTION_PREFIX = "home_h_"


def build_content(shortcuts):
    content = []

    for key, heading, matches in SECTIONS:
        rows = [row for row in shortcuts if matches(row)]
        if not rows:
            continue

        content.append({
            "id": SECTION_PREFIX + key,
            "type": "header",
            "data": {"text": '<span class="h4"><b>%s</b></span>' % heading, "col": 12},
        })
        content += [
            {
                "id": "home_sc_%s_%s" % (key, index),
                "type": "shortcut",
                "data": {"shortcut_name": row["label"], "col": 3},
            }
            for index, row in enumerate(rows)
        ]

    return content


def _rebuild_home_workspace():
    if frappe.db.exists("Workspace", WORKSPACE):
        doc = frappe.get_doc("Workspace", WORKSPACE)
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = WORKSPACE
        doc.title = WORKSPACE

    doc.title = WORKSPACE
    doc.label = WORKSPACE
    doc.module = ""
    doc.public = 1
    doc.is_hidden = 0
    doc.sequence_id = 0
    doc.icon = "home"

    shortcuts = _seed_shortcuts()
    doc.set("shortcuts", shortcuts)
    doc.set("custom_blocks", [])

    doc.content = json.dumps(build_content(shortcuts))
    doc.flags.ignore_permissions = True
    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)
    return len(shortcuts)


def _drop_legacy_block():
    if frappe.db.exists("Custom HTML Block", LEGACY_BLOCK):
        frappe.delete_doc("Custom HTML Block", LEGACY_BLOCK, force=True,
                          ignore_permissions=True, delete_permanently=True)


def set_default_workspace_for_users():
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		pluck="name",
	)
	for user in users:
		frappe.db.set_value("User", user, "default_workspace", WORKSPACE, update_modified=False)
	return len(users)


def _skip_sync() -> bool:
    return bool(
        frappe.flags.in_migrate
        or frappe.flags.in_install
        or frappe.flags.in_patch
        or frappe.flags.in_import
        or frappe.flags.in_test
    )


def on_workspace_update(doc, method=None):
    if _skip_sync() or doc.name in (WORKSPACE, "Welcome Workspace"):
        return
    if not doc.public or not is_custom(doc.module):
        return

    previous = doc.get_doc_before_save()
    if not previous:
        return

    was_hidden = bool(previous.get("is_hidden"))
    now_hidden = bool(doc.is_hidden)
    if was_hidden == now_hidden:
        return

    label = doc.title or doc.name
    slug = frappe.scrub(label).replace("_", "-")

    _sync_tile(
        wanted=not now_hidden,
        label=label,
        section="workspace",
        tile={"type": "URL", "label": label, "url": f"/app/{slug}",
              "color": COLOURS["workspace"]},
        note=f"{label} was un-hidden, so it now appears on Home.",
    )


def on_report_change(doc, method=None):
    if _skip_sync():
        return
    if not is_custom(doc.module):
        return

    label = doc.report_name or doc.name

    _sync_tile(
        wanted=not doc.disabled,
        label=label,
        section="report",
        tile={"type": "Report", "label": label, "link_to": doc.name,
              "color": COLOURS["report"]},
        note=f"New report {label} added to Home.",
    )


def on_page_change(doc, method=None):
    if _skip_sync():
        return
    if not is_custom(doc.module):
        return

    label = doc.title or doc.name

    _sync_tile(
        wanted=True,
        label=label,
        section="page",
        tile={"type": "Page", "label": label, "link_to": doc.name,
              "color": COLOURS["page"]},
        note=f"New page {label} added to Home.",
    )


def on_trash(doc, method=None):
    if _skip_sync():
        return

    for label in _candidate_labels(doc):
        _sync_tile(wanted=False, label=label, section=None, tile=None, note=None)


def after_rename(doc, method=None, old_name=None, merge=False):
    if _skip_sync():
        return

    for label in _candidate_labels(doc, extra=[old_name]):
        _sync_tile(wanted=False, label=label, section=None, tile=None, note=None)

    handler = {
        "Report": on_report_change,
        "Page": on_page_change,
    }.get(doc.doctype)
    if handler:
        handler(doc)


def _candidate_labels(doc, extra=None) -> list:
    labels = [
        doc.get("title"),
        doc.get("report_name"),
        doc.get("dashboard_name"),
        doc.name,
    ]
    labels += extra or []
    return [label for label in labels if label]


def _sync_tile(wanted: bool, label: str, section, tile, note):
    try:
        home = frappe.get_doc("Workspace", WORKSPACE)
        existing = [row for row in home.shortcuts if (row.label or "") == label]

        if wanted and existing:
            return
        if not wanted and not existing:
            return

        blocks = json.loads(home.content or "[]")

        if wanted:
            home.append("shortcuts", tile)
            blocks = _insert_into_section(blocks, section, label)
        else:
            home.set(
                "shortcuts",
                [row.as_dict() for row in home.shortcuts if (row.label or "") != label],
            )
            blocks = _drop_from_content(blocks, [label])

        home.content = json.dumps(blocks)
        _save_home(home)

        if note:
            home.add_comment("Info", note)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Home tile sync failed for {label}")


def _section_heading(key) -> str:
    for section_key, heading, _matches in SECTIONS:
        if section_key == key:
            return heading
    return key.title()


def _insert_into_section(blocks, section, label):
    header_id = SECTION_PREFIX + section
    tile_block = {
        "id": f"home_sc_{section}_{frappe.generate_hash(length=6)}",
        "type": "shortcut",
        "data": {"shortcut_name": label, "col": 3},
    }

    start = next(
        (index for index, block in enumerate(blocks) if block.get("id") == header_id), None
    )

    if start is None:
        heading = {
            "id": header_id,
            "type": "header",
            "data": {
                "text": '<span class="h4"><b>%s</b></span>' % _section_heading(section),
                "col": 12,
            },
        }
        order = [key for key, _heading, _matches in SECTIONS]
        position = len(blocks)
        if section in order:
            later = order[order.index(section) + 1 :]
            for index, block in enumerate(blocks):
                block_id = str(block.get("id", ""))
                if any(block_id == SECTION_PREFIX + key for key in later):
                    position = index
                    break
        return blocks[:position] + [heading, tile_block] + blocks[position:]

    end = start + 1
    while end < len(blocks) and blocks[end].get("type") == "shortcut":
        end += 1

    return blocks[:end] + [tile_block] + blocks[end:]


def _drop_from_content(blocks, labels):
    lowered = {label.lower() for label in labels if label}

    kept = [
        block
        for block in blocks
        if not (
            block.get("type") == "shortcut"
            and str((block.get("data") or {}).get("shortcut_name", "")).lower() in lowered
        )
    ]

    pruned = []
    for index, block in enumerate(kept):
        is_heading = str(block.get("id", "")).startswith(SECTION_PREFIX)
        if is_heading:
            following = kept[index + 1] if index + 1 < len(kept) else None
            if not following or following.get("type") != "shortcut":
                continue
        pruned.append(block)

    return pruned


def _save_home(home):
    home.flags.ignore_permissions = True
    home.flags.ignore_links = True
    home.save(ignore_permissions=True)
