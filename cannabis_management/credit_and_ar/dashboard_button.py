import frappe

PAGE = "ar-weekly-review"
LABEL = "AR Accountability"

_ICON = (
	'<svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7'
	'a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-5 9l2 2 4-4"/></svg>'
)

BLOCKS = {
	"CEO": "ceo",
	"Nikki": "nd",
}

ACCENT = "#6b46c1"
ACCENT_HOVER = "#59379f"

_IOV_ICON = (
	'<svg viewBox="0 0 24 24"><path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5M12 13v8"/></svg>'
)

EXTRA_BUTTONS = {
	"CEO": [("iov", "inventory-overview", "Inventory Overview", _IOV_ICON, "#2f7d4f", "#25663f")],
}


def _button_html(prefix, suffix="arw", page=PAGE, label=LABEL, icon=_ICON):
	return (
		f'      <button class="{prefix}-refresh-btn {prefix}-{suffix}-btn"\n'
		f'              title="Open the {label} page"\n'
		f'              onclick="frappe.set_route(\'{page}\')">\n'
		f'        {icon}\n'
		f'        {label}\n'
		f'      </button>\n'
	)


def _button_css(prefix, suffix="arw", label=LABEL, accent=ACCENT, hover=ACCENT_HOVER):
	return f"""

/* {label} button — shares .{prefix}-refresh-btn's shape, accented so it reads
   as an action in the header. Injected by
   credit_and_ar/dashboard_button.py on after_migrate. */
.{prefix}-{suffix}-btn {{
  background: {accent};
  border-color: {accent};
  color: #fff;
  margin-right: 8px;
}}
.{prefix}-{suffix}-btn:hover {{
  background: {hover};
  border-color: {hover};
  color: #fff;
}}
"""


def install():
	if not frappe.db.exists("Page", PAGE):
		return

	for block_name, prefix in BLOCKS.items():
		try:
			_install_one(block_name, prefix)
		except Exception:
			frappe.log_error(
				f"Could not add the {LABEL} button to the {block_name} block",
				"AR Weekly Review button",
			)


def _install_one(block_name, prefix):
	if not frappe.db.exists("Custom HTML Block", block_name):
		return

	doc = frappe.get_doc("Custom HTML Block", block_name)
	buttons = [("arw", PAGE, LABEL, _ICON, ACCENT, ACCENT_HOVER)] + EXTRA_BUTTONS.get(block_name, [])
	changed = False

	for suffix, page, label, icon, accent, hover in buttons:
		if not frappe.db.exists("Page", page):
			continue
		marker = f"{prefix}-{suffix}-btn"
		html = doc.html or ""

		anchor = f'<button class="{prefix}-refresh-btn"'
		linked = f'href="/app/{page}"' in html
		if marker not in html and not linked and anchor in html:
			doc.html = html.replace(anchor, _button_html(prefix, suffix, page, label, icon).lstrip() + "      " + anchor, 1)
			changed = True

		if marker in (doc.html or "") and f".{marker} {{" not in (doc.style or ""):
			doc.style = (doc.style or "") + _button_css(prefix, suffix, label, accent, hover)
			changed = True

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
