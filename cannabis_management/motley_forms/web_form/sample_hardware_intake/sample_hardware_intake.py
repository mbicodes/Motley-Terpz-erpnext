# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
#
# Frappe imports this module for every standard Web Form
# (web_form.get_web_form_module), so it has to exist even when there is no
# extra context to add — without it the page 500s on ModuleNotFoundError.

import frappe


def get_context(context):
	pass
