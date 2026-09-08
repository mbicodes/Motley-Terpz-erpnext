# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""Timesheet document guards for the Manufacturing Timesheet Kiosk.

The kiosk's verification photos live in Long Text fields on the Timesheet itself
rather than as File attachments, precisely so there is nothing to detach
independently of the document (see custom_fields.py for the fuller reasoning). That
storage choice, plus permlevel PHOTO_PERMLEVEL with write granted to no role at all,
read_only=1 and allow_on_submit=0, already means nobody can *clear* a photo through
Desk, a bulk edit, a Data Import or the REST API.

It leaves exactly one way to lose one: delete the whole Timesheet. Eleven roles hold
`delete` on Timesheet on this site - HR User, Manufacturing User, CEO, Accounts User,
Projects User, Employee Self Service and several per-person roles - so trimming
permissions is not a durable answer; the next role someone adds would reopen it. The
on_trash guard below closes it for everyone instead, whoever is asking.
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
	"""Refuse to delete a Timesheet that carries a kiosk verification photo.

	This runs for *every* delete path, not just the Desk button: the list view's
	bulk delete, `frappe.client.delete`, and the REST API all go through
	frappe.model.delete_doc, which calls on_trash before it checks links.
	``force=True`` only skips those link checks, so it does not get around this.
	(``ignore_on_trash=True`` does, but it is a Python-only argument - no UI or HTTP
	route can pass it, so reaching it already means server console access, at which
	point raw SQL is available anyway and no document hook could help.)

	Cancelling is deliberately still allowed. A cancelled Timesheet stops counting
	towards hours but keeps its row - and its photos - on record, which is the
	correction path this guard points people at. The amended copy carries no photo
	(the fields are no_copy), so the only Timesheet holding a given photo is always
	the one the kiosk actually wrote it to.
	"""
	if doc.doctype != "Timesheet":
		return

	on_record = [field for field in PHOTO_FIELDS if doc.get(field)]
	if not on_record:
		return

	frappe.throw(
		_(
			"{0} carries a kiosk verification photo, which is a permanent record and "
			"cannot be deleted by anyone. Cancel the Timesheet instead - a cancelled "
			"Timesheet stops counting towards hours but keeps its photo on record."
		).format(doc.name),
		title=_("Verification photo on record"),
	)
