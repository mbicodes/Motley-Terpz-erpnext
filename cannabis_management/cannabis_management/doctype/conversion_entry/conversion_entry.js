// /home/frappeuser/frappe-bench/apps/cannabis_management/cannabis_management/cannabis_management/doctype/conversion_entry/conversion_entry.js
frappe.ui.form.on('Conversion Entry', {
    refresh: function (frm) {
        // Ensure the CSS is (re)‑injected whenever the form is refreshed
        make_child_table_scrollable(frm);
    }

    // // In case the child table is added dynamically (e.g. via a custom button)
    // items_add: function (frm) {
    //     make_child_table_scrollable(frm);
    // }
});

/**
 * Injects CSS that makes the "Items" child table horizontally scrollable
 * while keeping the heading row fixed to the scroll container.
 */
// function make_child_table_scrollable(frm) {
//     // Only run once per page load
//     if ($('#conversion-entry-items-scroll').length) return;

//     // The selector targets the outer .form-grid that contains both heading & body
//     const css = `
//         /* --------------------------------------------------------------
//            Scroll container – wraps heading + body so they scroll together
//            -------------------------------------------------------------- */
//         .frappe-control[data-fieldname="items"] .form-grid {
//             overflow-x: auto !important;
//             /* Prevent the grid from shrinking below its content width */
//             min-width: max-content;
//         }

//         /* --------------------------------------------------------------
//            Force heading row and each data row to size to their content
//            -------------------------------------------------------------- */
//         .frappe-control[data-fieldname="items"] .grid-heading-row,
//         .frappe-control[data-fieldname="items"] .grid-row {
//             display: flex !important;
//             width: max-content !important;
//             min-width: 100% !important;   /* fallback for very narrow screens */
//         }

//         /* --------------------------------------------------------------
//            Ensure the rows container also expands to its content width
//            -------------------------------------------------------------- */
//         .frappe-control[data-fieldname="items"] .grid-body .rows {
//             width: max-content !important;
//             min-width: 100% !important;
//         }

//         /* --------------------------------------------------------------
//            Fixed column widths – adjust these values to match your layout
//            -------------------------------------------------------------- */
//         .frappe-control[data-fieldname="items"] .grid-static-col,
//         .frappe-control[data-fieldname="items"] .grid-heading-row .grid-static-col {
//             flex: 0 0 150px !important;   /* column label width */
//             width: 150px !important;
//         }

//         /* Smaller widths for the row‑check and row‑index columns */
//         .frappe-control[data-fieldname="items"] .row-check,
//         .frappe-control[data-fieldname="items"] .row-index {
//             flex: 0 0 40px !important;
//             width: 40px !important;
//         }
//     `;

//     $('<style id="conversion-entry-items-scroll">')
//         .prop('type', 'text/css')
//         .html(css)
//         .appendTo('head');
// }


frappe.ui.form.on("Conversion Entry Item", {
    conversion_type: function (frm, cdt, cdn) {
        clear_hidden_fields_for_row(frm, cdt, cdn);
    }
});

function clear_hidden_fields_for_row(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    let ct = row.conversion_type;
    if (!ct) return;

    if (!["2 to 1", "2 to 2", "3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_2", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_2", 0);
    }
    if (!["3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_3", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_3", 0);
    }
    if (!["4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_4", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_4", 0);
    }
    if (!["5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_5", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_5", 0);
    }
    if (!["6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_6", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_6", 0);
    }
    if (ct !== "7 to 1") {
        frappe.model.set_value(cdt, cdn, "raw_material_7", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_7", 0);
    }
    if (!["1 to 2", "2 to 2"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "finished_good_2", "");
        frappe.model.set_value(cdt, cdn, "qty_fg_2", 0);
    }
}