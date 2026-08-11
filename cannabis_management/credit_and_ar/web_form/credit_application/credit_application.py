import frappe


def get_context(context):
	"""Context for the public Credit Application web form."""
	context.no_cache = 1