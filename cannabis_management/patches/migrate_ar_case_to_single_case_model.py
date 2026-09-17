"""AR Case moves from five case types (Warning, Hard Hold, Immediate Hold,
Payment Plan, Workout) and a six-value status to one case per customer —
opened only for Hard Hold, with a binary Active/Closed status and a
Resolution (Release / Payment Plan / Workout) recorded on the same case.

Runs in ``pre_model_sync``, before the DocType sync drops the ``case_type``
and ``company`` columns and narrows ``status`` to its new options, so the old
values are still readable straight off the table.

* ``status``: Cured / Released / Defaulted / Closed -> Closed; Open / Active
  stays Active — except a Warning case, which is always closed: Warning no
  longer has a case behind it at all.
* ``resolution``: blank, unless the case was already Active on a Payment Plan
  or Workout (case_type), or is being closed on the strength of an existing
  Released record (release_basis/released_by already set) — that becomes
  ``Release``.
* ``trigger_reason``: re-mapped onto the same vocabulary as Customer > Hold
  Reason, via the existing ``HOLD_REASON_BY_TRIGGER`` table. Anything with no
  mapping (e.g. a hand-typed "Manual") is left blank rather than guessed.
"""

import frappe


def execute():
	if not frappe.db.table_exists("AR Case"):
		return
	if not frappe.db.has_column("AR Case", "case_type"):
		# Already migrated (or a fresh site that never had the old schema).
		return

	from cannabis_management.credit_and_ar import utils

	# The DocType sync that adds the ``resolution`` column has not run yet —
	# this patch is pre_model_sync, specifically so ``case_type`` is still
	# readable. Add the column by hand so the values below have somewhere to
	# land; the sync that follows will find it already there.
	if not frappe.db.has_column("AR Case", "resolution"):
		frappe.db.sql_ddl("ALTER TABLE `tabAR Case` ADD COLUMN `resolution` varchar(140) DEFAULT ''")

	rows = frappe.db.sql(
		"""
		SELECT name, case_type, status, trigger_reason, release_basis, released_by
		FROM `tabAR Case`
		""",
		as_dict=True,
	)

	closed_statuses = {"Cured", "Released", "Defaulted", "Closed"}

	for row in rows:
		new_status = "Closed" if row.status in closed_statuses else "Active"

		resolution = ""
		if row.case_type == "Warning":
			# Warning never has a case of its own going forward.
			new_status = "Closed"
		elif new_status == "Active" and row.case_type == "Payment Plan":
			resolution = "Payment Plan"
		elif new_status == "Active" and row.case_type == "Workout":
			resolution = "Workout"
		elif new_status == "Closed" and (row.release_basis or row.released_by):
			resolution = "Release"

		trigger_reason = utils.HOLD_REASON_BY_TRIGGER.get(row.trigger_reason, "")

		frappe.db.sql(
			"""
			UPDATE `tabAR Case`
			SET status = %(status)s, resolution = %(resolution)s, trigger_reason = %(reason)s
			WHERE name = %(name)s
			""",
			{
				"status": new_status,
				"resolution": resolution,
				"reason": trigger_reason,
				"name": row.name,
			},
		)

	frappe.db.commit()
