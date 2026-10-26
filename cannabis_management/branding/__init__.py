"""Motley Terpz branding, kept in code so a migrate can never lose it.

Everything the login page, the "Time's up!" screen and the desk chrome show as
Motley Terpz used to live only in database settings, typed in through the UI.
This module holds the same values and re-applies them after every migrate
(and hourly, the way the other self-healing enforcers in hooks.py run):

  Website Settings   app name, logos, favicon, brand HTML, "Powered by" footer,
                     and head_html (branding/head.html): the logo badge on the
                     login card plus the "Time's up!" page shown after the
                     45-minute idle logout (idle_logout.py / public/js/idle_logout.js)
  Login Page         custom_theme's login settings: title, logo, background, colours
  Navbar Settings    the desk navbar logo
  Uploaded files     the logos and login background those settings point at are
                     restored from branding/files/ if they ever go missing from
                     the site, at the same URLs

Only values that differ are written, so a run with nothing to fix is a few
reads. To change the branding, change it HERE and migrate: an edit made only
through the UI is put back by the next migrate.

"ERPNext" -> "MotleyERP": every user-facing string containing "ERPNext" gets an
English Translation record, the same mechanism that already shows "Salary Slip"
as "Check Stubs" here. It changes the text people read and never a name the
system uses, so the "ERPNext CRM Settings" doctype, routes and links keep
working. The strings are collected from the code of every installed app, so
new ones arriving with an update are covered by the next migrate.
"""

import os
import shutil

import frappe

BRAND = "MotleyERP"
COPYRIGHT_SOURCE = "&copy; Frappe Technologies Pvt. Ltd. and contributors"
COPYRIGHT = "&copy; Motley Terpz LLC"

HERE = os.path.dirname(__file__)

SETTINGS = {
	"Website Settings": {
		"app_name": "Motley Terpz",
		"app_logo": "/private/files/FULL_LOGO.png",
		"banner_image": "/private/files/FULL_LOGO4a4432.png",
		"splash_image": "/private/files/FULL_LOGO.png",
		"favicon": "/files/Motley-Terpz-Web-Logo.png",
		"brand_html": "<img src='/files/FULL_LOGO.png' Style ='max-height:500px;'>\n\n ",
		"title_prefix": "MT",
		# Replaces the default "Powered by ERPNext" in the website footer.
		"footer_powered": f"Powered by {BRAND}",
	},
	"Login Page": {
		"title": "Motley Terpz",
		"welcome_text": "Welcome to Motley Terpz",
		"description": "By All tech Virtual",
		"logo": "/files/Motley-Terpz-Web-Logo.png",
		"bg_image": "/files/cdc-XLhDvfz0sUM-unsplash.jpg",
		"login_card_color": "#8d58bf",
		"footer_color": "#8d58bf",
	},
	"Navbar Settings": {
		"app_logo": "/private/files/FULL_LOGO6f0335.png",
	},
}


def ensure_branding():
	"""after_migrate / hourly. Re-applies SETTINGS, head_html and the files."""
	_restore_files()

	wanted = {k: dict(v) for k, v in SETTINGS.items()}
	with open(os.path.join(HERE, "head.html")) as f:
		wanted["Website Settings"]["head_html"] = f.read()

	changed = False
	for doctype, values in wanted.items():
		if not frappe.db.exists("DocType", doctype):
			continue  # Login Page ships with custom_theme
		for field, value in values.items():
			if (frappe.db.get_single_value(doctype, field) or "") != value:
				frappe.db.set_single_value(doctype, field, value)
				changed = True

	if _ensure_translation(COPYRIGHT_SOURCE, COPYRIGHT, overwrite=True):
		changed = True

	if changed:
		frappe.db.commit()
		frappe.clear_cache()


def _restore_files():
	"""Copy back any branding file missing from the site, at its old path."""
	for scope in ("public", "private"):
		src_dir = os.path.join(HERE, "files", scope)
		dest_dir = frappe.get_site_path(scope, "files")
		for name in os.listdir(src_dir):
			dest = os.path.join(dest_dir, name)
			if not os.path.exists(dest):
				os.makedirs(dest_dir, exist_ok=True)
				shutil.copy2(os.path.join(src_dir, name), dest)


# ── "ERPNext" -> "MotleyERP" ─────────────────────────────────────────────────

def rebrand(text):
	return text.replace("ERPNext", BRAND) if text else text


def queue_translation_sync():
	"""after_migrate. Collecting the strings reads every app's source (~40 s),
	so it goes to a worker instead of holding up the migrate."""
	try:
		frappe.enqueue(
			"cannabis_management.branding.sync_translations",
			queue="long",
			job_id="motley_brand_translations",
			deduplicate=True,
			enqueue_after_commit=False,
		)
	except Exception:
		sync_translations()


def sync_translations():
	"""Create the English Translation for every user-facing string that says
	ERPNext. Only missing ones are created: a translation someone wrote by hand
	for one of these strings is left as it is."""
	from frappe.translate import clear_cache, get_messages_for_app

	strings = set()
	for app in frappe.get_installed_apps():
		for m in get_messages_for_app(app):
			msg = m[1]
			context = m[2] if len(m) >= 4 and isinstance(m[2], str) else ""
			if isinstance(msg, str) and "ERPNext" in msg:
				strings.add((msg, context or ""))

	# Labels that exist only in the database: custom fields from fixtures or the UI.
	for f in frappe.get_all(
		"Custom Field",
		or_filters={"label": ["like", "%ERPNext%"], "description": ["like", "%ERPNext%"]},
		fields=["label", "description"],
	):
		for text in (f.label, f.description):
			if text and "ERPNext" in text:
				strings.add((text, ""))

	created = sum(_ensure_translation(src, rebrand(src), context=ctx) for src, ctx in sorted(strings))
	if created:
		frappe.db.commit()
		clear_cache()
	return created


def _ensure_translation(source, translated, context="", overwrite=False):
	"""Returns 1 when a record was created or changed."""
	from frappe.translate import clear_cache

	name = frappe.db.get_value(
		"Translation", {"language": "en", "source_text": source, "context": context or ["is", "not set"]}
	)
	if name:
		if overwrite and frappe.db.get_value("Translation", name, "translated_text") != translated:
			frappe.db.set_value("Translation", name, "translated_text", translated)
			clear_cache()
			return 1
		return 0
	frappe.get_doc(
		{
			"doctype": "Translation",
			"language": "en",
			"source_text": source,
			"translated_text": translated,
			"context": context or None,
		}
	).insert(ignore_permissions=True)
	return 1


@frappe.whitelist()
def get_versions():
	"""Override of frappe.utils.change_log.get_versions for the About dialog,
	which prints each app's title as-is rather than through translation."""
	from frappe.utils.change_log import get_versions as frappe_get_versions

	versions = frappe_get_versions()
	for v in versions.values():
		v["title"] = rebrand(v.get("title"))
	return versions
