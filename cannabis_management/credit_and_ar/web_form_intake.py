"""Intake helpers for applications that arrive through the public web form.

A prospect filling in the public form has no Customer record yet, and none is
created here on their behalf — Finance links or creates the Customer by hand
once the file is reviewed. Draft applications sit with `customer` blank.

Wire it up in hooks.py:

    doc_events = {
        "Credit Application": {
            "before_insert": "cannabis_management.credit_and_ar.web_form_intake.before_insert",
        }
    }
"""

import frappe


def before_insert(doc, method=None):
	if not _is_web_form_submission():
		return

	doc.application_type = doc.application_type or "New"


def _is_web_form_submission() -> bool:
	if frappe.form_dict.get("web_form"):
		return True
	return getattr(frappe.local, "request", None) is not None and frappe.session.user == "Guest"