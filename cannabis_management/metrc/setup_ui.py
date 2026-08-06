# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Build the METRC workspace, number cards, charts and report.

    bench --site <site> execute cannabis_management.metrc.setup_ui.setup

Split from install.py because these are presentation artifacts: re-running them
must never touch schema, and a site that wants the sync without the dashboard
can skip this entirely.

The workspace is the answer to "is compliance healthy right now?" - counts
first, then the lists behind them.
"""

import json

import frappe

WORKSPACE = "METRC"
MODULE = "Cannabis Management"


# ---------------------------------------------------------------------------
# Number cards
# ---------------------------------------------------------------------------

# (label, doctype, filters, colour)
# Number Card autonames from `label`, so the label IS the record name.
# Every label is METRC-prefixed to stay identifiable and avoid colliding
# with cards other modules may already have created.
CARDS = [
    # --- Inventory coverage -------------------------------------------------
    (
        "METRC Items Synced",
        "Item",
        {"custom_metrc_item_id": [">", 0]},
        "#2f6f4f",
    ),
    (
        "METRC Items Tracked",
        "Item",
        {"custom_metrc_tracked": 1},
        "#1c5f8a",
    ),
    (
        "METRC Items Need Review",
        "Item",
        {"custom_metrc_auto_created": 1},
        "#d99b1c",
    ),
    # --- Tags ---------------------------------------------------------------
    ("METRC Tags Total", "Metric Tag", {}, "#1c5f8a"),
    (
        "METRC Tags Unused",
        "Metric Tag",
        {"status": "Unused"},
        "#2f6f4f",
    ),
    (
        "METRC Tags Active",
        "Metric Tag",
        {"custom_metrc_status": "Active"},
        "#2f6f4f",
    ),
    (
        "METRC Packages Synced",
        "Metric Tag",
        {"custom_metrc_package_id": [">", 0]},
        "#1c5f8a",
    ),
    # --- Push health --------------------------------------------------------
    (
        "METRC Invoices Synced",
        "Sales Invoice",
        {"custom_metrc_sync_status": "Synced"},
        "#2f6f4f",
    ),
    (
        "METRC Invoices Pending",
        "Sales Invoice",
        {"custom_metrc_sync_status": ["in", ["Queued", "Failed"]]},
        "#d99b1c",
    ),
    (
        "METRC Invoices Failed",
        "Sales Invoice",
        {"custom_metrc_sync_status": "Parked"},
        "#c0392b",
    ),
    (
        "METRC Deliveries Synced",
        "Delivery Note",
        {"custom_metrc_sync_status": "Synced"},
        "#2f6f4f",
    ),
    # --- Queue --------------------------------------------------------------
    (
        "METRC Outbox Queued",
        "Metrc Outbox",
        {"status": ["in", ["Queued", "Failed"]]},
        "#d99b1c",
    ),
    (
        "METRC Outbox Parked",
        "Metrc Outbox",
        {"status": "Parked"},
        "#c0392b",
    ),
    (
        "METRC Outbox Success",
        "Metrc Outbox",
        {"status": "Success"},
        "#2f6f4f",
    ),
    # --- Health -------------------------------------------------------------
    (
        "METRC API Errors",
        "Metrc API Log",
        {"response_status": [">=", 400]},
        "#c0392b",
    ),
    (
        "METRC Cursors Failing",
        "Metrc Sync State",
        {"last_status": "Failed"},
        "#c0392b",
    ),
]


def _filters_json(doctype, filters):
    """Number Card stores filters as JSON rows of [doctype, field, operator, value].

    The first element must be the actual doctype name. Passing None there
    renders the card as an error rather than a count, because Frappe
    concatenates it into the query.
    """
    out = []
    for field, value in (filters or {}).items():
        if isinstance(value, list) and len(value) == 2:
            out.append([doctype, field, value[0], value[1]])
        else:
            out.append([doctype, field, "=", value])
    return json.dumps(out)


def create_number_cards():
    print("Creating METRC number cards...")
    made = 0
    for label, doctype, filters, colour in CARDS:
        if not frappe.db.exists("DocType", doctype):
            continue
        if frappe.db.exists("Number Card", label):
            # Keep filters current on re-run; labels/colours may have changed.
            frappe.db.set_value(
                "Number Card",
                label,
                {"filters_json": _filters_json(doctype, filters), "color": colour},
                update_modified=False,
            )
            continue

        doc = frappe.get_doc(
            {
                "doctype": "Number Card",
                "name": label,
                "label": label,
                "type": "Document Type",
                "document_type": doctype,
                "function": "Count",
                "filters_json": _filters_json(doctype, filters),
                "is_public": 1,
                "show_percentage_stats": 0,
                "color": colour,
                "module": MODULE,
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        made += 1
    print(f"  + {made} number card(s) created, {len(CARDS)} total refreshed")


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------


def create_charts():
    name = "METRC API Activity"
    if frappe.db.exists("Dashboard Chart", name):
        print(f"  = Chart {name} (exists)")
        return
    doc = frappe.get_doc(
        {
            "doctype": "Dashboard Chart",
            "name": name,
            "chart_name": name,
            "chart_type": "Count",
            "document_type": "Metrc API Log",
            "based_on": "timestamp",
            "time_interval": "Daily",
            "timespan": "Last Month",
            "type": "Line",
            "is_public": 1,
            "module": MODULE,
            # Mandatory on Dashboard Chart even when unfiltered.
            "filters_json": "[]",
            "dynamic_filters_json": "[]",
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    print(f"  + Chart {name}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def create_variance_report():
    name = "Metrc Variance"
    if frappe.db.exists("Report", name):
        print(f"  = Report {name} (exists)")
        return
    doc = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": name,
            "ref_doctype": "Metric Tag",
            "report_type": "Script Report",
            "module": MODULE,
            "is_standard": "No",
            "disabled": 0,
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    print(f"  + Report {name}")


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


def _content():
    """Workspace layout: health first, then coverage, then the lists."""

    def card(name, col=3):
        return {"type": "number_card", "data": {"number_card_name": name, "col": col}}

    def header(text, col=12):
        return {"type": "header", "data": {"text": text, "col": col}}

    def para(text, col=12):
        return {"type": "paragraph", "data": {"text": text, "col": col}}

    blocks = [
        header(
            '<span class="h4"><b>METRC Compliance</b></span>'
        ),
        para(
            "California seed-to-sale reporting. METRC is the system of record for "
            "compliance state &mdash; where the two systems disagree, the difference is a "
            "variance to investigate, never an automatic overwrite."
        ),
        {"type": "spacer", "data": {"col": 12}},
        header('<span class="h6"><b>Push health</b></span>'),
        card("METRC Invoices Synced"),
        card("METRC Deliveries Synced"),
        card("METRC Outbox Queued"),
        card("METRC Outbox Parked"),
        {"type": "spacer", "data": {"col": 12}},
        header('<span class="h6"><b>Inventory coverage</b></span>'),
        card("METRC Items Synced"),
        card("METRC Items Tracked"),
        card("METRC Items Need Review"),
        card("METRC Packages Synced"),
        {"type": "spacer", "data": {"col": 12}},
        header('<span class="h6"><b>Tag pool</b></span>'),
        card("METRC Tags Total"),
        card("METRC Tags Unused"),
        card("METRC Tags Active"),
        card("METRC Invoices Failed"),
        {"type": "spacer", "data": {"col": 12}},
        header('<span class="h6"><b>System health</b></span>'),
        card("METRC API Errors"),
        card("METRC Cursors Failing"),
        card("METRC Outbox Success"),
        card("METRC Invoices Pending"),
        {"type": "spacer", "data": {"col": 12}},
        {"type": "chart", "data": {"chart_name": "METRC API Activity", "col": 12}},
        {"type": "spacer", "data": {"col": 12}},
        header('<span class="h6"><b>Open</b></span>'),
        {"type": "card", "data": {"card_name": "Configuration", "col": 4}},
        {"type": "card", "data": {"card_name": "Monitoring", "col": 4}},
        {"type": "card", "data": {"card_name": "Inventory", "col": 4}},
    ]
    return json.dumps(blocks)


def _links():
    return [
        {"type": "Card Break", "label": "Configuration", "onboard": 0, "hidden": 0},
        {
            "type": "Link",
            "label": "Metrc Settings",
            "link_type": "DocType",
            "link_to": "Metrc Settings",
            "onboard": 1,
            "description": "Keys, facilities, UOM map, auto-create and dry-run switches.",
        },
        {"type": "Card Break", "label": "Monitoring", "onboard": 0, "hidden": 0},
        {
            "type": "Link",
            "label": "Metrc Outbox",
            "link_type": "DocType",
            "link_to": "Metrc Outbox",
            "description": "Queued and failed writes. Parked rows need a human.",
        },
        {
            "type": "Link",
            "label": "Metrc Sync State",
            "link_type": "DocType",
            "link_to": "Metrc Sync State",
            "description": "One forward-only cursor per licence and endpoint.",
        },
        {
            "type": "Link",
            "label": "Metrc API Log",
            "link_type": "DocType",
            "link_to": "Metrc API Log",
            "description": "Every request and response, for audit and debugging.",
        },
        {
            "type": "Link",
            "label": "Metrc Variance",
            "link_type": "Report",
            "link_to": "Metrc Variance",
            "dependencies": "Metric Tag",
            "is_query_report": 1,
            "description": "Where METRC and the stock ledger disagree.",
        },
        {"type": "Card Break", "label": "Inventory", "onboard": 0, "hidden": 0},
        {
            "type": "Link",
            "label": "Metric Tag",
            "link_type": "DocType",
            "link_to": "Metric Tag",
            "description": "The tag registry - one row per physical METRC label.",
        },
        {
            "type": "Link",
            "label": "Batch",
            "link_type": "DocType",
            "link_to": "Batch",
            "description": "The ERPNext side of a METRC package.",
        },
        {
            "type": "Link",
            "label": "Item",
            "link_type": "DocType",
            "link_to": "Item",
            "description": "Flag tracked items and review auto-created ones.",
        },
    ]


def _shortcuts():
    """Filtered shortcuts - one click to the list that matters."""
    return [
        {
            "type": "DocType",
            "link_to": "Metrc Outbox",
            "label": "Parked Writes",
            "color": "Red",
            "stats_filter": json.dumps({"status": "Parked"}),
        },
        {
            "type": "DocType",
            "link_to": "Item",
            "label": "Items to Review",
            "color": "Orange",
            "stats_filter": json.dumps({"custom_metrc_auto_created": 1}),
        },
        {
            "type": "DocType",
            "link_to": "Sales Invoice",
            "label": "Invoices Not Synced",
            "color": "Orange",
            "stats_filter": json.dumps(
                {"custom_metrc_sync_status": ["in", ["Queued", "Failed", "Parked"]]}
            ),
        },
        {
            "type": "DocType",
            "link_to": "Metric Tag",
            "label": "Unused Tags",
            "color": "Green",
            "stats_filter": json.dumps({"status": "Unused"}),
        },
        {
            "type": "Report",
            "link_to": "Metrc Variance",
            "label": "Variance Report",
            "color": "Grey",
            # doc_view must stay blank for a Report shortcut; "Report" is not a
            # valid DocType View and Frappe rejects the whole workspace.
            "is_query_report": 1,
        },
    ]


def create_workspace(force=True):
    """Create or rebuild the METRC workspace.

    force=True replaces the existing one. The workspace is generated content,
    not user content, so rebuilding it on upgrade is the intended behaviour -
    but anyone who has customised it should pass force=False.
    """
    if frappe.db.exists("Workspace", WORKSPACE):
        if not force:
            print(f"  = Workspace {WORKSPACE} (left alone)")
            return
        frappe.delete_doc("Workspace", WORKSPACE, force=1, ignore_permissions=True)
        frappe.db.commit()

    doc = frappe.get_doc(
        {
            "doctype": "Workspace",
            "name": WORKSPACE,
            "label": WORKSPACE,
            "title": WORKSPACE,
            "module": MODULE,
            "icon": "shield",
            "indicator_color": "green",
            "public": 1,
            "is_hidden": 0,
            "sequence_id": 40,
            "content": _content(),
            "links": _links(),
            "shortcuts": _shortcuts(),
            "number_cards": [
                {"number_card_name": label} for label, *_ in CARDS
            ],
            "charts": [{"chart_name": "METRC API Activity", "label": "METRC API Activity"}],
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    print(f"  + Workspace {WORKSPACE} ({len(CARDS)} cards, {len(_shortcuts())} shortcuts)")


def setup(force_workspace=True):
    create_variance_report()
    create_number_cards()
    create_charts()
    frappe.db.commit()
    create_workspace(force=force_workspace)
    frappe.db.commit()
    frappe.clear_cache()
    print("\nMetrc UI installed.")
