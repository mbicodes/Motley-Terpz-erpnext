"""
Build the "Sales Target and Inventory Dashboard" Custom HTML Block by combining
two existing Frappe Pages:
  - sales-target-dashboa  (Sales Target Dashboard)
  - inventory-sales-dashboard (Inventory Sales Dashboard)

Custom HTML Blocks render inside a Shadow DOM (frappe.create_shadow_element):
  * <script>/<style> tags are stripped from the `html` field -> CSS goes in `style`.
  * the script runs in an IIFE with `root_element` = the shadowRoot.
  * document.getElementById/querySelector(All) do NOT see shadow content;
    they must target `root_element` (ShadowRoot supports getElementById +
    querySelector(All)). Real-document calls (createElement, body.appendChild,
    execCommand) stay on `document`.

This script adapts both page controllers to that model and assembles one block.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.build_sales_target_inventory_block.run
"""
import re
import frappe

BASE = "/home/frappeuser/frappe-bench/apps/cannabis_management/cannabis_management/cannabis_management/page"
INV_JS = f"{BASE}/inventory_sales_dashboard/inventory_sales_dashboard.js"
ST_JS = f"{BASE}/sales_target_dashboa/sales_target_dashboa.js"
ST_CSS = f"{BASE}/sales_target_dashboa/sales_target_dashboa.css"

BLOCK_NAME = "Sales Target and Inventory Dashboard"


def _read(path):
    with open(path) as f:
        return f.read()


def _scope_inventory_js(js):
    """Point shadow-DOM-bound DOM queries at root_element; leave real-document calls alone."""
    js = js.replace("document.getElementById(", "root_element.getElementById(")
    js = js.replace("document.querySelectorAll(", "root_element.querySelectorAll(")
    js = js.replace("document.querySelector(", "root_element.querySelector(")
    return js


def build():
    # ── Inventory page: split CSS / HTML / JS out of page.main.html(`...`) ──
    inv = _read(INV_JS)
    _, _, after = inv.partition("page.main.html(`")
    tpl, _, inv_js_after = after.partition("`);")
    _, _, after_style = tpl.partition("<style>")
    inv_css, _, inv_html = after_style.partition("</style>")

    inv_js_body = inv_js_after.rstrip()
    if inv_js_body.endswith("};"):            # drop the on_page_load closer
        inv_js_body = inv_js_body[:-2].rstrip()
    inv_js_body = _scope_inventory_js(inv_js_body)

    inv_iife = "(function() {\n" + inv_js_body + "\n})();"

    # ── Sales-target page: extract HTML from getDashboardHTML(), body from on_page_load ──
    st = _read(ST_JS)
    st_css = _read(ST_CSS)

    # HTML
    _, _, gh = st.partition("function getDashboardHTML() {")
    _, _, gh2 = gh.partition("return `")
    st_html, _, _ = gh2.partition("`;")

    # on_page_load body
    _, _, body = st.partition("function (wrapper) {")
    body, _, _ = body.partition("\nfunction getDashboardHTML()")
    body = body.rstrip()
    if body.endswith("};"):
        body = body[:-2].rstrip()

    # strip page-specific bits that don't exist in a Custom HTML Block
    body = re.sub(r"var page = frappe\.ui\.make_app_page\(\{.*?\}\);", "", body, count=1, flags=re.S)
    body = body.replace("$(wrapper).find('.layout-main-section').html(getDashboardHTML());", "")
    body = body.replace("wrapper.querySelector('.sd-dash')", "root_element.querySelector('.sd-dash')")
    # set_primary_action is a single line; drop the whole line (regex across it is unsafe
    # because the nested function body contains its own ");").
    body = "\n".join(l for l in body.split("\n") if "page.set_primary_action" not in l)

    st_iife = "(function() {\n" + body.strip() + "\n})();"

    # ── Assemble the three fields ──
    html_field = (
        "<!-- ===== SALES TARGET DASHBOARD ===== -->\n"
        + st_html.strip()
        + "\n\n<!-- ===== INVENTORY SALES DASHBOARD ===== -->\n"
        + inv_html.strip()
    )
    style_field = (
        "/* ===== INVENTORY SALES DASHBOARD CSS ===== */\n"
        + inv_css.strip()
        + "\n\n/* ===== SALES TARGET DASHBOARD CSS ===== */\n"
        + st_css.strip()
    )
    script_field = (
        "/* ===== SALES TARGET DASHBOARD ===== */\n"
        + st_iife
        + "\n\n/* ===== INVENTORY SALES DASHBOARD ===== */\n"
        + inv_iife
    )
    return html_field, script_field, style_field


def run():
    frappe.set_user("Administrator")
    html_field, script_field, style_field = build()

    if frappe.db.exists("Custom HTML Block", BLOCK_NAME):
        doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)
        doc.html = html_field
        doc.script = script_field
        doc.style = style_field
        doc.private = 0
        doc.save(ignore_permissions=True)
        action = "Updated"
    else:
        doc = frappe.new_doc("Custom HTML Block")
        doc.__newname = BLOCK_NAME
        doc.html = html_field
        doc.script = script_field
        doc.style = style_field
        doc.private = 0
        doc.insert(ignore_permissions=True)
        action = "Created"

    frappe.db.commit()
    print(f"{action}: Custom HTML Block '{doc.name}'")
    print(f"  html   : {len(html_field):,} chars")
    print(f"  script : {len(script_field):,} chars")
    print(f"  style  : {len(style_field):,} chars")
