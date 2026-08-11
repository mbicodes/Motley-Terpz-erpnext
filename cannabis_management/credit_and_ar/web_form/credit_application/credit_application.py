import frappe


def get_context(context):
	"""Context for the public Credit Application web form."""
	context.no_cache = 1
	# Keep this client-facing page's title clean — skip the sitewide "MT -" prefix.
	context.title_prefix = None