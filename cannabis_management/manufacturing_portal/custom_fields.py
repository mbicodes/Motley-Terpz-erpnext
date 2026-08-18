"""Custom field definitions for the Manufacturing Portal module.

Applied idempotently by ``cannabis_management.patches.install_manufacturing_portal``
so a plain ``bench migrate`` reproduces them on any site, and exported through the
app's existing unfiltered Custom Field fixture.

Storage note: the code is stored as plain text in a Data field, deliberately, so an
administrator can read a worker their code back off the User form. It is NOT hashed.
See the module README for why hashing a short code buys very little, and what the
real protections are (uniqueness, rate limiting, lockout, restricted session, audit
log).
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Minimum length is enforced in the User validate hook rather than by the field, so
# the message can explain itself.
MIN_CODE_LENGTH = 6

USER_FIELDS = [
	{
		"fieldname": "custom_manufacturing_portal_section",
		"fieldtype": "Section Break",
		"label": "Manufacturing Portal",
		"insert_after": "assistant_enabled",
		"collapsible": 1,
	},
	{
		"fieldname": "custom_process_code",
		"fieldtype": "Data",
		"label": "Manufacturing Portal Code",
		"insert_after": "custom_manufacturing_portal_section",
		"no_copy": 1,
		"description": (
			"Code this person types at /manufacturing-process to unlock the page. "
			f"Minimum {MIN_CODE_LENGTH} characters, must be unique across all users, "
			"and cannot be a single repeated character or a run like 123456. "
			"Leave blank to deny access."
		),
	},
	{
		"fieldname": "custom_process_code_enabled",
		"fieldtype": "Check",
		"label": "Manufacturing Portal Access Enabled",
		"insert_after": "custom_process_code",
		"default": "0",
		"description": (
			"Both a code and this checkbox are required. Unticking revokes access "
			"immediately without destroying the code."
		),
	},
]

CUSTOM_FIELDS = {"User": USER_FIELDS}


def install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
