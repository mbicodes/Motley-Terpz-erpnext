"""Document events this module needs, merged into the app's own.

Wired this way rather than by editing the four doc_events blocks in hooks.py
directly: Sales Order, Delivery Note, Payment Entry and Conversion Entry all
already carry handlers from other modules, several as bare strings rather than
lists. Merging in code appends without touching a line anyone else owns, and
normalises the string form so no existing handler is ever dropped.
"""

MT_DISPATCH_DOC_EVENTS = {
	"Sales Order": {
		"on_submit": ["cannabis_management.mt_dispatch.flow.on_so_submit"],
		"on_update_after_submit": [
			"cannabis_management.mt_dispatch.flow.on_so_update",
			"cannabis_management.mt_dispatch.events.on_so_change",
		],
		"before_update_after_submit": ["cannabis_management.mt_dispatch.flow.guard_stage_field"],
		"on_cancel": ["cannabis_management.mt_dispatch.flow.on_so_cancel"],
	},
	"Delivery Note": {
		"before_insert": ["cannabis_management.mt_dispatch.gates.dn_before_insert"],
		"after_insert": [
			"cannabis_management.mt_dispatch.flow.dn_after_insert",
			"cannabis_management.mt_dispatch.events.on_dn_insert",
		],
		"before_submit": ["cannabis_management.mt_dispatch.gates.dn_before_submit"],
		"on_submit": ["cannabis_management.mt_dispatch.flow.dn_on_submit"],
		"on_cancel": ["cannabis_management.mt_dispatch.flow.on_dn_cancel"],
	},
	"Conversion Entry": {
		"on_submit": [
			"cannabis_management.mt_dispatch.flow.on_conversion_submit",
			"cannabis_management.mt_dispatch.events.on_ce_change",
		],
		"on_cancel": [
			"cannabis_management.mt_dispatch.flow.on_conversion_cancel",
			"cannabis_management.mt_dispatch.events.on_ce_change",
		],
	},
	"Sales Invoice": {
		"after_insert": ["cannabis_management.mt_dispatch.events.on_si_insert"],
		"on_submit": ["cannabis_management.mt_dispatch.events.on_si_submit"],
		"on_cancel": ["cannabis_management.mt_dispatch.events.on_si_cancel"],
	},
	"Payment Entry": {
		"on_submit": ["cannabis_management.mt_dispatch.payments.on_pe_change"],
		"on_cancel": ["cannabis_management.mt_dispatch.payments.on_pe_change"],
	},
	"Dispatch Company Settings": {
		"on_update": ["cannabis_management.mt_dispatch.settings.clear_settings_cache"],
	},
}


def extend_doc_events(doc_events):
	"""Merge in place. Appends, never replaces."""
	for doctype, events in MT_DISPATCH_DOC_EVENTS.items():
		target = doc_events.setdefault(doctype, {})
		for event, handlers in events.items():
			existing = target.get(event, [])
			if isinstance(existing, str):
				existing = [existing]
			target[event] = list(existing) + [h for h in handlers if h not in existing]
	return doc_events


MT_DISPATCH_CRON = {
	# Section 9.1: reminders every 15 minutes, and the morning digest inside it.
	"*/15 * * * *": ["cannabis_management.mt_dispatch.reminders.run"],
}

MT_DISPATCH_DOCTYPE_JS = {
	"Sales Order": ["mt_dispatch/public/sales_order_dispatch.js"],
	"Delivery Note": ["mt_dispatch/public/delivery_note_dispatch.js"],
}


def extend_scheduler_events(scheduler_events):
	cron = scheduler_events.setdefault("cron", {})
	for pattern, handlers in MT_DISPATCH_CRON.items():
		existing = cron.get(pattern, [])
		if isinstance(existing, str):
			existing = [existing]
		cron[pattern] = list(existing) + [h for h in handlers if h not in existing]
	return scheduler_events


def extend_doctype_js(doctype_js):
	for doctype, scripts in MT_DISPATCH_DOCTYPE_JS.items():
		existing = doctype_js.get(doctype, [])
		if isinstance(existing, str):
			existing = [existing]
		doctype_js[doctype] = list(existing) + [s for s in scripts if s not in existing]
	return doctype_js
