import frappe

REMOVED_WORKSPACES = [
	"Stock",
	"Assets",
	"Projects",
	"Users",
	"Payroll",
	"Website",
	"Tools",
	"ERPNext Settings",
	"Integrations",
	"ERPNext Integrations",
]


def remove_unwanted_workspaces():
	deleted = []

	for name in REMOVED_WORKSPACES:
		if not frappe.db.exists("Workspace", name):
			continue
		try:
			frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)
			deleted.append(name)
		except Exception:
			frappe.log_error(
				title="Workspace cleanup failed", message=f"Could not delete Workspace {name}"
			)

	if deleted:
		frappe.db.commit()
		frappe.clear_cache()
		print(f"Removed workspaces from sidebar: {', '.join(deleted)}")

	return deleted

AR_WEEKLY_STUB = "AR Weekly Review"
AR_WEEKLY_STUB_USER = "__route-stub__"


def ensure_ar_weekly_review_stub():
    if frappe.db.exists("Workspace", AR_WEEKLY_STUB):
        if frappe.db.get_value("Workspace", AR_WEEKLY_STUB, "public"):
            frappe.db.set_value(
                "Workspace",
                AR_WEEKLY_STUB,
                {"public": 0, "for_user": AR_WEEKLY_STUB_USER, "is_hidden": 1},
                update_modified=False,
            )
            frappe.db.commit()
            frappe.clear_cache()
            print(f"Demoted Workspace {AR_WEEKLY_STUB} to private so it stops shadowing the page")
        return

    frappe.get_doc(
        {
            "doctype": "Workspace",
            "label": AR_WEEKLY_STUB,
            "title": f"{AR_WEEKLY_STUB} (route stub)",
            "public": 0,
            "for_user": AR_WEEKLY_STUB_USER,
            "is_hidden": 1,
            "content": "[]",
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache()
    print(f"Created private route stub Workspace {AR_WEEKLY_STUB}")

RENAMED_WORKSPACE_STUBS = [
    "METRC",
]


def ensure_renamed_workspace_stubs():
    created = []
    for name in RENAMED_WORKSPACE_STUBS:
        if frappe.db.exists("Workspace", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": name,
                "title": f"{name} (route stub)",
                "public": 0,
                "for_user": AR_WEEKLY_STUB_USER,
                "is_hidden": 1,
                "content": "[]",
            }
        ).insert(ignore_permissions=True)
        created.append(name)

    if created:
        frappe.db.commit()
        frappe.clear_cache()
        print(f"Created private route stub Workspace(s): {', '.join(created)}")
