# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ConversionStatus(Document):
	"""Master list behind Conversion Entry's Conversion Status field.

	Named after the status itself (autoname field:status_name) so the value
	stored on a Conversion Entry reads as the status, not an opaque ID.
	Retire a status with `disabled` rather than deleting it — deleting would
	break the link on every entry that already used it.
	"""

	pass
