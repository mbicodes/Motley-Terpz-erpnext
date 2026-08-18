"""Create the "Manufacturing Portal" section + fields (custom_process_code,
custom_process_code_enabled) on User — the code-entry credential the
/manufacturing-process portal's Access Code screen checks.

Idempotent: cannabis_management.manufacturing_portal.custom_fields.install()
just calls create_custom_fields, which no-ops on fields that already exist.
"""

from cannabis_management.manufacturing_portal.custom_fields import install


def execute():
	install()
