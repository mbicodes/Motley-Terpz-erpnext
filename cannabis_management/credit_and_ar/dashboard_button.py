# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Puts an "AR Weekly Review" button in the dashboard header blocks.

Why this is a hook and not a one-off edit: the "Nikki" Custom HTML Block is
shipped in fixtures/custom_html_block.json, so sync_fixtures rewrites it from
the fixture on every migrate and any direct edit to the record is lost. The
"CEO" block is not in that fixture, so an edit there survives — but it would
then live only in this site's database and never reach another instance.

Running from after_migrate solves both: it is version-controlled, it deploys
with the app, and it gets the last word because after_migrate runs after
sync_fixtures. Same reasoning as customer_layout.enforce and
notifications.install_notifications, which are wired up for the same reason.

Idempotent: a block that already carries the button is left alone, so this is
safe to run on every migrate.
"""

import frappe

PAGE = "ar-weekly-review"
LABEL = "AR Weekly Review"

_ICON = (
	'<svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7'
	'a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-5 9l2 2 4-4"/></svg>'
)

# block name -> css prefix already used by that dashboard's header buttons.
# The new button reuses the block's own <prefix>-refresh-btn class so it
# inherits that dashboard's exact shape, font and icon sizing; only the accent
# is added here.
BLOCKS = {
	"CEO": "ceo",
	"Nikki": "nd",
}

ACCENT = "#6b46c1"
ACCENT_HOVER = "#59379f"


def _button_html(prefix):
	return (
		f'      <button class="{prefix}-refresh-btn {prefix}-arw-btn"\n'
		f'              title="Open the {LABEL} page"\n'
		f'              onclick="frappe.set_route(\'{PAGE}\')">\n'
		f'        {_ICON}\n'
		f'        {LABEL}\n'
		f'      </button>\n'
	)


def _button_css(prefix):
	return f"""

/* {LABEL} button — shares .{prefix}-refresh-btn's shape, accented so it reads
   as the primary action in the header. Injected by
   credit_and_ar/dashboard_button.py on after_migrate. */
.{prefix}-arw-btn {{
  background: {ACCENT};
  border-color: {ACCENT};
  color: #fff;
}}
.{prefix}-arw-btn:hover {{
  background: {ACCENT_HOVER};
  border-color: {ACCENT_HOVER};
  color: #fff;
}}
"""


def install():
	"""after_migrate hook — see the module docstring."""
	if not frappe.db.exists("Page", PAGE):
		# Nothing to link to yet; a later migrate will pick it up.
		return

	for block_name, prefix in BLOCKS.items():
		try:
			_install_one(block_name, prefix)
		except Exception:
			# A dashboard button must never be the reason a migrate fails.
			frappe.log_error(
				f"Could not add the {LABEL} button to the {block_name} block",
				"AR Weekly Review button",
			)


def _install_one(block_name, prefix):
	if not frappe.db.exists("Custom HTML Block", block_name):
		return

	doc = frappe.get_doc("Custom HTML Block", block_name)
	marker = f"{prefix}-arw-btn"
	changed = False

	# The header's own Refresh button is the anchor — the new button goes
	# immediately before it, inside the same actions row.
	anchor = f'<button class="{prefix}-refresh-btn"'
	if marker not in (doc.html or "") and anchor in (doc.html or ""):
		doc.html = doc.html.replace(anchor, _button_html(prefix).lstrip() + "      " + anchor, 1)
		changed = True

	if f".{marker} {{" not in (doc.style or ""):
		doc.style = (doc.style or "") + _button_css(prefix)
		changed = True

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
