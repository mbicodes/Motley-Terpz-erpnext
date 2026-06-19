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

# Route of the standalone Inventory Sales Dashboard page.
INVENTORY_ROUTE = "/app/inventory-sales-dashboard"

# Button shown where the embedded Inventory dashboard used to be. Clicking it
# opens the full Inventory Sales Dashboard page instead of rendering it inline.
INVENTORY_BUTTON_HTML = f"""
<!-- ===== INVENTORY DASHBOARD LINK ===== -->
<div class="invlink-wrap">
  <a class="invlink-btn" href="{INVENTORY_ROUTE}">
    <span class="invlink-icon">📦</span>
    <span class="invlink-text">
      <span class="invlink-title">Open Inventory Dashboard</span>
      <span class="invlink-sub">View the full Inventory Sales Dashboard</span>
    </span>
    <span class="invlink-arrow">&rarr;</span>
  </a>
</div>
"""

INVENTORY_BUTTON_CSS = """
/* ===== INVENTORY DASHBOARD LINK CSS ===== */
.invlink-wrap { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; max-width:1280px; margin:0 auto; padding:8px 24px; }
.invlink-btn {
  display:flex; align-items:center; gap:16px; text-decoration:none;
  background:linear-gradient(135deg,#1E3A8A 0%,#2563EB 60%,#3B82F6 100%);
  border-radius:12px; padding:18px 22px; box-shadow:0 1px 3px rgba(0,0,0,.08);
  transition:transform .12s ease, box-shadow .12s ease;
}
.invlink-btn:hover { transform:translateY(-1px); box-shadow:0 6px 18px rgba(37,99,235,.28); }
.invlink-icon { width:44px; height:44px; flex-shrink:0; background:rgba(255,255,255,.18); border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:22px; }
.invlink-text { display:flex; flex-direction:column; gap:3px; flex:1; }
.invlink-title { font-size:17px; font-weight:700; color:#fff; }
.invlink-sub { font-size:12.5px; color:rgba(255,255,255,.82); }
.invlink-arrow { font-size:22px; color:#fff; font-weight:700; flex-shrink:0; }
"""


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
    # The Inventory Sales Dashboard is no longer embedded inline; it lives on its
    # own page and is reached via a button (see INVENTORY_BUTTON_* above).

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
    # Inventory dashboard replaced by a button linking to its standalone page.
    html_field = (
        "<!-- ===== SALES TARGET DASHBOARD ===== -->\n"
        + st_html.strip()
        + "\n\n"
        + INVENTORY_BUTTON_HTML.strip()
    )
    style_field = (
        INVENTORY_BUTTON_CSS.strip()
        + "\n\n/* ===== SALES TARGET DASHBOARD CSS ===== */\n"
        + st_css.strip()
    )
    script_field = (
        "/* ===== SALES TARGET DASHBOARD ===== */\n"
        + st_iife
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
