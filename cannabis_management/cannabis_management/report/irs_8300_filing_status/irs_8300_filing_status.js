frappe.query_reports["IRS 8300 Filing Status"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "customer",
            label: "Customer",
            fieldtype: "Link",
            options: "Customer",
        },
        {
            fieldname: "filing_status",
            label: "Filing Status",
            fieldtype: "Select",
            options: "\nPending\nReported\nFiled - E-File\nFiled - Paper\nOverdue",
        },
    ],

    get_datatable_options(options) {
        return Object.assign(options, {
            getRowHTML(cells, props) {
                const row_data = props.row;
                // Find filing_status cell
                const status_cell = cells.find(c => c && c.column &&
                    c.column.fieldname === 'filing_status');
                const status = status_cell && status_cell.content;

                let row_style = '';
                if (status === 'Reported') {
                    row_style = 'background-color: #d4edda;';  // green
                } else if (status === 'Overdue') {
                    row_style = 'background-color: #f8d7da;';  // red
                } else if (status === 'Pending') {
                    row_style = 'background-color: #fff3cd;';  // yellow
                }

                return `<tr style="${row_style}">${cells.join('')}</tr>`;
            }
        });
    },

    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "days_left") {
            if (data.has_attachment) {
                value = `<span style="color:green; font-weight:bold;">✅ Reported</span>`;
            } else if (data.days_left < 0) {
                value = `<span style="color:red; font-weight:bold;">${data.days_left} (OVERDUE)</span>`;
            } else if (data.days_left <= 3) {
                value = `<span style="color:orange; font-weight:bold;">${data.days_left}</span>`;
            } else {
                value = `<span style="color:green;">${data.days_left}</span>`;
            }
        }

        if (column.fieldname === "filing_status") {
            const colors = {
                "Pending":        "#856404",
                "Overdue":        "red",
                "Reported":       "green",
                "Filed - E-File": "green",
                "Filed - Paper":  "green",
            };
            const bg = {
                "Pending":        "#fff3cd",
                "Overdue":        "#f8d7da",
                "Reported":       "#d4edda",
                "Filed - E-File": "#d4edda",
                "Filed - Paper":  "#d4edda",
            };
            const c  = colors[data.filing_status] || "gray";
            const b  = bg[data.filing_status] || "#f0f0f0";
            value = `<span style="
                color:${c};
                background:${b};
                font-weight:bold;
                padding: 2px 8px;
                border-radius: 4px;
            ">${data.filing_status}</span>`;
        }

        if (column.fieldname === "has_attachment") {
            value = data.has_attachment
                ? `<span style="color:green;">✅</span>`
                : `<span style="color:#ccc;">—</span>`;
        }

        return value;
    }
};