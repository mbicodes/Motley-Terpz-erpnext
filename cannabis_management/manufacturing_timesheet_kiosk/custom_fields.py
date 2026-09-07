"""Custom field definitions for the Manufacturing Timesheet Kiosk module.

Applied idempotently from ``after_migrate`` (see hooks.py) so a plain ``bench migrate``
reproduces the field on any site - the same pattern used by
``cannabis_management.manufacturing_portal.custom_fields``.

Storage note: the code is stored as plain text in a Data field, deliberately, matching
the Manufacturing Portal's access code - not hashed, not a Password field. This makes
the kiosk's login lookup and the uniqueness check in ``employee_hooks.py`` plain,
indexed-friendly DB queries instead of a decrypt-and-compare loop over every employee.
An administrator can also read a worker's code back off the Employee form if they
forget it. See that module's README for the fuller reasoning; it applies here too.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

EMPLOYEE_FIELDS = [
	{
		"fieldname": "custom_kiosk_access_code",
		"fieldtype": "Data",
		"label": "Kiosk Access Code",
		"insert_after": "status",
		"no_copy": 1,
		"description": (
			"Personal access code / PIN this employee types at the Manufacturing "
			"Process timesheet kiosk to clock in/out. Must be unique across all "
			"employees. Leave blank to deny kiosk access."
		),
	},
]

CUSTOM_FIELDS = {"Employee": EMPLOYEE_FIELDS}


def install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
