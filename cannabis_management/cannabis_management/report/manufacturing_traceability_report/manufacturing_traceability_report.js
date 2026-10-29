frappe.query_reports["Manufacturing Traceability Report"] = {

    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "custom_project",
            label: __("Project / Batch"),
            fieldtype: "Link",
            options: "Project",
        },
        {
            fieldname: "work_order",
            label: __("Work Order"),
            fieldtype: "Link",
            options: "Work Order",
        },
        {
            fieldname: "finished_item",
            label: __("Finished Item"),
            fieldtype: "Link",
            options: "Item",
            get_query: function () {
                return { filters: { is_stock_item: 1 } };
            },
        },
        {
            fieldname: "wo_status",
            label: __("WO Status"),
            fieldtype: "Select",
            options: "\nNot Started\nIn Process\nCompleted\nStopped\nCancelled",
        },
        {
            fieldname: "raw_material",
            label: __("Raw Material"),
            fieldtype: "Link",
            options: "Item",
            get_query: function () {
                return { filters: { is_stock_item: 1 } };
            },
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "wo_status" && data) {
            const status = data.wo_status;
            if (status === "Completed") {
                value = `<span style="color: #2e7d32; font-weight: bold;">${value}</span>`;
            } else if (status === "In Process") {
                value = `<span style="color: #f57c00; font-weight: bold;">${value}</span>`;
            } else if (status === "Stopped" || status === "Cancelled") {
                value = `<span style="color: #c62828; font-weight: bold;">${value}</span>`;
            } else if (status === "Not Started") {
                value = `<span style="color: #1565c0; font-weight: bold;">${value}</span>`;
            }
        }

        if (column.fieldname === "remaining_transfer_qty" && data) {
            const val = parseFloat(data.remaining_transfer_qty);
            if (val < 0) {
                value = `<span style="color: #c62828;">${value}</span>`;
            } else if (val === 0) {
                value = `<span style="color: #2e7d32;">${value}</span>`;
            }
        }

        if (column.fieldname === "yield_pct" && data) {
            const val = parseFloat(data.yield_pct);
            if (val < 80) {
                value = `<span style="color: #c62828; font-weight: bold;">${value}</span>`;
            } else if (val >= 95) {
                value = `<span style="color: #2e7d32;">${value}</span>`;
            }
        }

        if (column.fieldname === "cost_variance" && data) {
            const val = parseFloat(data.cost_variance);
            if (val > 0) {
                value = `<span style="color: #c62828;">${value}</span>`;
            } else if (val < 0) {
                value = `<span style="color: #2e7d32;">${value}</span>`;
            }
        }

        if (column.fieldname === "qty_variance" && data) {
            const val = parseFloat(data.qty_variance);
            if (val > 0) {
                value = `<span style="color: #f57c00;">${value}</span>`;
            }
        }

        return value;
    },

    onload: function (report) {
        report.page.add_inner_button(__("Refresh"), function () {
            report.refresh();
        });
    },
};
