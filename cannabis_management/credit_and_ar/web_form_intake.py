import frappe
from frappe.utils.file_manager import save_file

CREDIT_AGREEMENT_WEB_FORM = "credit-agreement"
CREDIT_AGREEMENT_PRINT_FORMAT = "Credit Agreement"

WEB_FORM_STARTING_STATE = "Finance Review"


def before_insert(doc, method=None):
	if not _is_web_form_submission():
		return

	doc.application_type = doc.application_type or "New"


def after_insert(doc, method=None):
	if _is_web_form_submission():
		_advance_to_finance_review(doc)

	if frappe.form_dict.get("web_form") != CREDIT_AGREEMENT_WEB_FORM:
		return

	doctype, name = doc.doctype, doc.name
	frappe.db.after_commit.add(lambda: _attach_agreement_pdf(doctype, name))


def _advance_to_finance_review(doc):
	frappe.db.set_value(doc.doctype, doc.name, "workflow_state", WEB_FORM_STARTING_STATE, update_modified=False)
	doc.workflow_state = WEB_FORM_STARTING_STATE


def _attach_agreement_pdf(doctype, name):
	original_user = frappe.session.user
	try:
		frappe.session.user = "Administrator"
		doc = frappe.get_doc(doctype, name)
		pdf_content = frappe.get_print(
			doctype, name, print_format=CREDIT_AGREEMENT_PRINT_FORMAT, doc=doc, as_pdf=True
		)
		save_file(
			fname=f"credit-agreement-{name}.pdf",
			content=pdf_content,
			dt=doctype,
			dn=name,
			folder="Home",
			is_private=1,
		)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Credit Agreement PDF attach failed")
	finally:
		frappe.session.user = original_user


def _is_web_form_submission() -> bool:
	if frappe.form_dict.get("web_form"):
		return True
	return getattr(frappe.local, "request", None) is not None and frappe.session.user == "Guest"
