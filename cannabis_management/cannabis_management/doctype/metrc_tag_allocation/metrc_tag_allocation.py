# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Safety cap so a mistyped range can't expand into a runaway number of rows.
MAX_RANGE = 5000

# Child statuses that count as "consumed" (no longer usable/available).
CONSUMED_STATUSES = {"Assigned", "Void", "Used Externally"}


class METRCTagAllocation(Document):
	def validate(self):
		self.recompute()

	def before_submit(self):
		# Expand the range into child rows the first time the doc is submitted.
		if not self.tags:
			self.expand_range()
		self.recompute()

	def on_update_after_submit(self):
		# validate() does not run when a submitted doc is saved, so recompute the
		# counters here (e.g. after tags are assigned/voided post-submit) and
		# persist them directly.
		self.recompute()
		frappe.db.set_value(
			self.doctype,
			self.name,
			{
				"total_tags": self.total_tags,
				"consumed": self.consumed,
				"available": self.available,
				"next_available_tag": self.next_available_tag,
				"status": self.status,
			},
			update_modified=False,
		)

	def on_cancel(self):
		self.db_set("status", "Void")

	# ── helpers ──────────────────────────────────────────────────────────────
	def expand_range(self):
		if not (self.range_start and self.range_end):
			frappe.throw(_("Range Start and Range End are required to expand tags."))

		ids = expand_tag_range(self.range_start, self.range_end)
		if len(ids) > MAX_RANGE:
			frappe.throw(
				_("This range expands to {0} tags, over the {1} limit.").format(len(ids), MAX_RANGE)
			)

		self.set("tags", [])
		for tag_id in ids:
			self.append("tags", {"tag_id": tag_id, "tag_status": "Available"})

	def recompute(self):
		"""Derive the read-only counters + status from the child rows."""
		rows = self.tags or []
		self.total_tags = len(rows)
		self.consumed = sum(1 for r in rows if r.tag_status in CONSUMED_STATUSES)
		self.available = sum(1 for r in rows if r.tag_status == "Available")
		self.next_available_tag = next(
			(r.tag_id for r in rows if r.tag_status == "Available"), None
		)

		# Void is a terminal state set on cancel — never auto-flip out of it.
		if self.status != "Void":
			self.status = "Exhausted" if (self.total_tags and not self.available) else "Active"

	@frappe.whitelist()
	def resync_tags(self):
		"""Recompute counters from the current child rows and stamp the sync time."""
		self.recompute()
		self.last_synced_on = now_datetime()
		self.save()
		return {
			"total_tags": self.total_tags,
			"consumed": self.consumed,
			"available": self.available,
			"next_available_tag": self.next_available_tag,
			"status": self.status,
		}


def expand_tag_range(start, end):
	"""Expand two METRC tag ids that share a prefix and differ only in a trailing
	numeric block, e.g. ...0000123 → ...0000130. If they can't be interpolated,
	fall back to just the two endpoints."""
	start = (start or "").strip()
	end = (end or "").strip()
	if not start:
		return []
	if not end or end == start:
		return [start]

	m1 = re.match(r"^(.*?)(\d+)$", start)
	m2 = re.match(r"^(.*?)(\d+)$", end)
	if not (m1 and m2) or m1.group(1) != m2.group(1):
		return [start, end]

	prefix = m1.group(1)
	width = len(m1.group(2))
	a, b = int(m1.group(2)), int(m2.group(2))
	if b < a:
		a, b = b, a
	return [f"{prefix}{str(n).zfill(width)}" for n in range(a, b + 1)]
