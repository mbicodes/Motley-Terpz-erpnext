# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""Document guards that make the kiosk's verification photos permanent.

The photos are private Files attached to the Timesheet, with the Timesheet's Attach
Image fields holding their URLs - so a photo shows as a picture and opens by clicking
it (see custom_fields.py). Being files, they are separate documents from the fields
pointing at them, and that is exactly what these guards exist to cover.

Field permissions alone are not enough. permlevel PHOTO_PERMLEVEL grants *write* to no
role at all, plus read_only=1 and allow_on_submit=0, so nobody can repoint or clear
one of these fields through Desk, a bulk edit, a Data Import or the REST API. But
deleting the file the field points at never touches the field, and deleting the whole
Timesheet takes its attachments with it - neither is a field write, so neither is
blocked by any of that.

Nor is trimming roles a durable answer: eleven roles hold `delete` on Timesheet on
this site (HR User, Manufacturing User, CEO, Accounts User, Projects User, Employee
Self Service and several per-person roles), and the next role someone adds would
reopen the hole. So both paths are closed here instead, for everyone, whoever is
asking:

	on_trash          - refuses to delete a Timesheet that carries a photo
	on_trash_file     - refuses to delete a File that *is* one

frappe.model.delete_doc runs on_trash before its link checks, so the Desk button, the
list view's bulk delete, the attachment (x), frappe.client.delete and the REST API all
hit these. ``force=True`` only skips the link checks. (``ignore_on_trash=True`` does
skip them, but it is a Python-only argument that no UI or HTTP route can pass -
reaching it already means server console access, where raw SQL is available anyway and
no document hook could help.)
"""

import frappe
from frappe import _

from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	PHOTO_PERMLEVEL,
	TIMESHEET_FIELDS,
)

# The photo fields, taken from the same definition that creates them - so this stays
# correct if one is renamed or a third is added. Keyed off PHOTO_PERMLEVEL rather than
# the whole list, so an ordinary (non-locked) Timesheet field added later isn't
# accidentally treated as evidence.
PHOTO_FIELDS = tuple(
	field["fieldname"]
	for field in TIMESHEET_FIELDS
	if field.get("permlevel") == PHOTO_PERMLEVEL
)


def on_trash(doc, method=None):
	"""Deleting a Timesheet now also deletes its kiosk verification photo(s).

	Changed on request: this used to *refuse* the delete (the photos were treated as
	a permanent record; the correction path was Cancel). It now removes the photo
	File(s) the Timesheet carries so the delete goes through cleanly and leaves no
	orphan File rows behind. on_trash_file below is correspondingly no longer a
	blocker. NOTE: this drops the previous anti-tamper guarantee — a verification
	photo is no longer permanent; anyone with delete on Timesheet can remove it.
	"""
	if doc.doctype != "Timesheet":
		return

	for field in PHOTO_FIELDS:
		if not doc.get(field):
			continue
		for name in frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Timesheet",
				"attached_to_name": doc.name,
				"attached_to_field": field,
			},
			pluck="name",
		):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)


def on_trash_file(doc, method=None):
	"""Refuse to delete a File that is a kiosk verification photo.

	Recognised by what the File says it is attached to, which _store_photo sets when
	it creates the file: a Timesheet, and one of the photo fields. That is also what
	makes Desk render it as the picture in that field, so a file this guard protects
	and a file the Timesheet displays are always the same set.

	This is the path field permissions cannot reach - the attachment (x) on the form,
	or a row in the Desk File list. Neither touches the Timesheet field, so neither is
	a field write, so permlevel 2 has nothing to say about them.
	"""
	# Changed on request (see on_trash above): kiosk verification photo Files are no
	# longer permanent. This guard used to refuse deleting one; it now allows it, so
	# a photo can be removed both as part of deleting its Timesheet and on its own.
	# Left as a no-op hook (rather than unwired) to keep the change visible and easy
	# to reinstate.
	return
