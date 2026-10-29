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
	_restore_files()

	wanted = {k: dict(v) for k, v in SETTINGS.items()}
	with open(os.path.join(HERE, "head.html")) as f:
		wanted["Website Settings"]["head_html"] = f.read()

	changed = False
	for doctype, values in wanted.items():
		if not frappe.db.exists("DocType", doctype):
			continue
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
	for scope in ("public", "private"):
		src_dir = os.path.join(HERE, "files", scope)
		dest_dir = frappe.get_site_path(scope, "files")
		for name in os.listdir(src_dir):
			dest = os.path.join(dest_dir, name)
			if not os.path.exists(dest):
				os.makedirs(dest_dir, exist_ok=True)
				shutil.copy2(os.path.join(src_dir, name), dest)


def rebrand(text):
	return text.replace("ERPNext", BRAND) if text else text


def queue_translation_sync():
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
	from frappe.translate import clear_cache, get_messages_for_app

	strings = set()
	for app in frappe.get_installed_apps():
		for m in get_messages_for_app(app):
			msg = m[1]
			context = m[2] if len(m) >= 4 and isinstance(m[2], str) else ""
			if isinstance(msg, str) and "ERPNext" in msg:
				strings.add((msg, context or ""))

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
	from frappe.utils.change_log import get_versions as frappe_get_versions

	versions = frappe_get_versions()
	for v in versions.values():
		v["title"] = rebrand(v.get("title"))
	return versions
