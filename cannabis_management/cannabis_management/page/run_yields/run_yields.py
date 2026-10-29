import frappe
from frappe.utils import getdate

from cannabis_management.cannabis_management.page.manufacturing_runs.manufacturing_runs import (
	JC_FROM,
	_build_run_row,
)

PAGE_ROLES = ("System Manager", "Manufacturing Manager", "Manufacturing User")


@frappe.whitelist()
def get_runs(from_date=None, to_date=None):
	frappe.only_for(PAGE_ROLES)

	having, params = [], {}
	if from_date:
		having.append("DATE(first_start) >= %(from_date)s")
		params["from_date"] = getdate(from_date)
	if to_date:
		having.append("DATE(first_start) <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	runs = frappe.db.sql(
		f"""
		SELECT wo.material_request AS run_id,
		       MIN(COALESCE(jc.actual_start_date, jc.creation)) AS first_start
		{JC_FROM}
		WHERE jc.status != 'Cancelled' AND jc.docstatus < 2
		  AND wo.material_request IS NOT NULL
		GROUP BY wo.material_request
		{"HAVING " + " AND ".join(having) if having else ""}
		ORDER BY first_start DESC
		""",
		params,
		as_dict=True,
	)

	rows = []
	for r in runs:
		row = _build_run_row(r.run_id)
		row["started_date"] = str(getdate(r.first_start))
		rows.append(row)
	return {"rows": rows}
