"""
Patch: Add Operating Costs table and client script to the Workstation DocType.
Safe to re-run.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    _create_custom_fields()
    _create_client_script()
    _create_server_script()
    frappe.db.commit()


def _create_custom_fields():
    create_custom_fields({
        "Workstation": [
            {
                "fieldname": "custom_operating_costs_section",
                "fieldtype": "Section Break",
                "label": "Operating Costs",
                "insert_after": "hour_rate",
            },
            {
                "fieldname": "custom_operating_costs",
                "fieldtype": "Table",
                "label": "Operating Costs",
                "options": "Workstation Operating Cost",
                "insert_after": "custom_operating_costs_section",
            },
            {
                "fieldname": "custom_total_operating_cost",
                "fieldtype": "Currency",
                "label": "Total Operating Cost (per hr)",
                "read_only": 1,
                "insert_after": "custom_operating_costs",
                "bold": 1,
            },
        ]
    }, ignore_validate=True)


def _create_client_script():
    script_name = "Workstation — Operating Cost Filter"
    if frappe.db.exists("Client Script", script_name):
        frappe.db.set_value("Client Script", script_name, "script", _client_script_code())
        return

    doc = frappe.get_doc({
        "doctype": "Client Script",
        "name": script_name,
        "dt": "Workstation",
        "script_type": "Form",
        "enabled": 1,
        "script": _client_script_code(),
    })
    doc.insert(ignore_permissions=True)


def _client_script_code():
    return """
frappe.ui.form.on('Workstation', {
    refresh(frm) {
        set_operating_component_filter(frm);
    }
});

function set_operating_component_filter(frm) {
    frm.fields_dict['custom_operating_costs'].grid.update_docfield_property(
        'operating_component', 'get_query', () => {
            return { filters: { is_active: 1 } };
        }
    );
}
"""


def _create_server_script():
    # Server-side validation via doc_events in hooks.py (already registered below)
    # Nothing to create here — handled in hooks.py
    pass
