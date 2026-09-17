"""Intake helpers for applications that arrive through the public web form.

A prospect filling in the public form has no Customer record yet, and none is
created here on their behalf — Finance links or creates the Customer by hand
once the file is reviewed. Draft applications sit with `customer` blank.

Wire it up in hooks.py:

    doc_events = {
        "Credit Application": {
            "before_insert": "cannabis_management.credit_and_ar.web_form_intake.before_insert",
            "after_insert": "cannabis_management.credit_and_ar.web_form_intake.after_insert",
        }
    }
"""

import frappe
from frappe.utils.file_manager import save_file

CREDIT_AGREEMENT_WEB_FORM = "credit-agreement"
CREDIT_AGREEMENT_PRINT_FORMAT = "Credit Agreement"

# A submission through this web form already carries the terms Sales agreed
# with the client (credit limit, payment terms, signatures) — it doesn't need
# the workflow's normal "Submit for Review" starting state, so it goes
# straight to Finance's queue.
WEB_FORM_STARTING_STATE = "Finance Review"


def before_insert(doc, method=None):
	if not _is_web_form_submission():
		return

	doc.application_type = doc.application_type or "New"
	# workflow_state is deliberately NOT set here. frappe.model.workflow.
	# validate_workflow hard-blocks a brand-new document from landing
	# anywhere but the workflow's first state ("Submit for Review") — for a
	# fresh insert it doesn't even consult role permissions, it just throws
	# ("transitioning directly to a state other than the first"). Moving it
	# to Finance Review has to happen as a real second transition after
	# insert instead — see _advance_to_finance_review, called below.


def after_insert(doc, method=None):
	if _is_web_form_submission():
		_advance_to_finance_review(doc)

	if frappe.form_dict.get("web_form") != CREDIT_AGREEMENT_WEB_FORM:
		return

	# Deferred to run after the whole request's transaction commits — see
	# _attach_agreement_pdf's docstring for why this can't run inline here.
	doctype, name = doc.doctype, doc.name
	frappe.db.after_commit.add(lambda: _attach_agreement_pdf(doctype, name))


def _advance_to_finance_review(doc):
	"""Move a fresh web-form submission straight to Finance Review.

	This deliberately does NOT go through a second `doc.save()` (as
	Administrator or otherwise) to make the transition — web_form.accept()
	still has more to do with this exact same in-memory `doc` after
	after_insert returns (attach fields with an uploaded file get a second
	`doc.save()` once the File records are created, to store their URLs).
	A competing save here would race that one: it bumps `modified` in the
	DB out from under the copy accept() is still holding, and that copy's
	own save() then fails Document.check_if_latest()'s timestamp check —
	silently, from this call site's point of view, but it means the
	attachment's file_url update never actually lands and the Attach field
	is left holding raw upload data instead of a working file. (Confirmed
	by hand: swap this for a `frappe.get_doc(...).save()` and submit a form
	with a License Document/Onboarding Packet file — both go blank.)

	A raw, unmodified-timestamp DB write sidesteps all of that: it commits
	the state immediately without disturbing `modified`, and syncing the
	in-memory doc's field means any later save() in the same request just
	re-persists the same value rather than reverting it.
	"""
	frappe.db.set_value(doc.doctype, doc.name, "workflow_state", WEB_FORM_STARTING_STATE, update_modified=False)
	doc.workflow_state = WEB_FORM_STARTING_STATE


def _attach_agreement_pdf(doctype, name):
	"""Attach a filled copy of the printed agreement to the record a client
	just created via the public Credit Agreement web form.

	This renders the "Credit Agreement" Print Format server-side with the
	values the client just submitted — the same template as the blank
	fillable PDF the agreement is based on — rather than a screenshot of the
	web page, so the attachment always matches the record exactly and never
	picks up page chrome (unsaved-state badges, autocomplete hints, etc.).

	Deliberately deferred (via frappe.db.after_commit, from after_insert)
	rather than run inline during insert: web_form.accept() still has more
	to do with its own in-memory copy of this doc after after_insert
	returns — an Attach field with an uploaded file gets a second
	`doc.save()` afterward, once the File record for it exists, to store
	its file_url. frappe.get_print() rendering the Print Format here — even
	read-only, on a *different* Document instance fetched by name — somehow
	leaves that later save() unable to persist its own changes: it reports
	success, but the Attach field reverts to the raw pre-upload value once
	reloaded from the DB. (Confirmed by hand: running this inline, even with
	no workflow_state change involved at all, is enough on its own to
	reproduce it — this isn't specific to _advance_to_finance_review.)
	Running this only after that whole request has already committed avoids
	the interaction entirely.

	By the time an after_commit callback runs, the Guest session accept()
	ran as has already been restored to whoever originally called it (or,
	for a raw anonymous request, torn down further still) — either way,
	nobody with a "print" permission on Credit Application. So this runs as
	Administrator, same as the workflow-state update above.
	"""
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
		# The application itself is already saved — a failed PDF attach
		# should never block or roll back that, just get logged for us.
		frappe.db.rollback()
		frappe.log_error(title="Credit Agreement PDF attach failed")
	finally:
		frappe.session.user = original_user


def _is_web_form_submission() -> bool:
	if frappe.form_dict.get("web_form"):
		return True
	return getattr(frappe.local, "request", None) is not None and frappe.session.user == "Guest"