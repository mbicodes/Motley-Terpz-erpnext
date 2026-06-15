class PaymentCalendar {
    constructor(wrapper, options = {}) {
        this.wrapper = wrapper;
        this.entity = options.entity || "All";
        this.current_month = options.month || new Date().getMonth() + 1;
        this.current_year = options.year || new Date().getFullYear();
        this.render_skeleton();
        this.load_data();
    }

    render_skeleton() {
        this.wrapper.innerHTML = `
            <div class="pc-container">
                <div class="pc-header">
                    <div class="pc-header-left">
                        <h3 class="pc-title">Payment Calendar</h3>
                        <div class="pc-legend">
                            <span class="pc-legend-item"><span class="pc-dot pc-dot-scheduled"></span> Scheduled</span>
                            <span class="pc-legend-item"><span class="pc-dot pc-dot-paid"></span> Paid</span>
                        </div>
                    </div>
                    <div class="pc-nav">
                        <button class="btn btn-xs btn-default pc-nav-btn" data-action="prev">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 12L6 8L10 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        </button>
                        <span class="pc-month-label"></span>
                        <button class="btn btn-xs btn-default pc-nav-btn" data-action="next">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 4L10 8L6 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        </button>
                        <button class="btn btn-xs btn-default pc-today-btn" data-action="today">Today</button>
                    </div>
                </div>
                <div class="pc-summary-bar"></div>
                <div class="pc-grid">
                    <div class="pc-weekdays">
                        <div class="pc-weekday">Sun</div>
                        <div class="pc-weekday">Mon</div>
                        <div class="pc-weekday">Tue</div>
                        <div class="pc-weekday">Wed</div>
                        <div class="pc-weekday">Thu</div>
                        <div class="pc-weekday">Fri</div>
                        <div class="pc-weekday">Sat</div>
                    </div>
                    <div class="pc-days"></div>
                </div>
            </div>
        `;

        this.wrapper.querySelectorAll(".pc-nav-btn, .pc-today-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                var action = btn.dataset.action;
                if (action === "prev") this.go_prev();
                else if (action === "next") this.go_next();
                else if (action === "today") this.go_today();
            });
        });
    }

    load_data() {
        var self = this;
        frappe.call({
            method: "cannabis_management.api.payment_calendar.get_payment_calendar",
            args: {
                month: self.current_month,
                year: self.current_year,
                entity: self.entity,
            },
            callback: function (r) {
                if (r.message) {
                    self.data = r.message;
                    self.render_calendar();
                }
            },
            error: function () {
                self.wrapper.querySelector(".pc-days").innerHTML =
                    '<div class="pc-error">Could not load calendar data</div>';
            },
        });
    }

    render_calendar() {
        var d = this.data;
        var self = this;

        this.wrapper.querySelector(".pc-month-label").textContent = d.month_label;

        var s = d.summary;
        this.wrapper.querySelector(".pc-summary-bar").innerHTML = `
            <div class="pc-summary-item pc-summary-scheduled">
                <span class="pc-summary-value">${self.fmt$(s.scheduled_total)}</span>
                <span class="pc-summary-label">${s.scheduled_count} scheduled</span>
            </div>
            <div class="pc-summary-item pc-summary-paid">
                <span class="pc-summary-value">${self.fmt$(s.paid_total)}</span>
                <span class="pc-summary-label">${s.paid_count} paid</span>
            </div>
            <div class="pc-summary-item pc-summary-total">
                <span class="pc-summary-value">${self.fmt$(s.scheduled_total + s.paid_total)}</span>
                <span class="pc-summary-label">total this month</span>
            </div>
        `;

        var days_container = this.wrapper.querySelector(".pc-days");
        days_container.innerHTML = "";

        for (var w = 0; w < d.calendar_weeks.length; w++) {
            var week = d.calendar_weeks[w];
            var week_row = document.createElement("div");
            week_row.className = "pc-week";

            for (var c = 0; c < week.length; c++) {
                var day = week[c];
                var cell = document.createElement("div");
                cell.className = "pc-day";

                if (!day) {
                    cell.classList.add("pc-day-empty");
                    week_row.appendChild(cell);
                    continue;
                }

                if (day.is_today) cell.classList.add("pc-day-today");

                var day_num = document.createElement("div");
                day_num.className = "pc-day-number";
                day_num.textContent = day.day;
                cell.appendChild(day_num);

                if (day.payments && day.payments.length > 0) {
                    cell.classList.add("pc-day-has-payments");
                    var pills = document.createElement("div");
                    pills.className = "pc-day-pills";

                    var show_count = Math.min(day.payments.length, 2);
                    for (var i = 0; i < show_count; i++) {
                        (function (p) {
                            var pill = document.createElement("div");
                            pill.className = "pc-pill pc-pill-" + p.status.toLowerCase();
                            pill.innerHTML =
                                '<span class="pc-pill-vendor">' + self.truncate(p.vendor, 14) + '</span>' +
                                '<span class="pc-pill-amount">' + self.fmt$(p.amount) + '</span>';
                            pill.title = p.vendor + "\n" + self.fmt$(p.amount) + "\n" + p.entity + " · " + p.status;
                            pill.addEventListener("click", function (e) {
                                e.stopPropagation();
                                if (p.name) frappe.set_route("Form", "Payment Entry", p.name);
                            });
                            pills.appendChild(pill);
                        })(day.payments[i]);
                    }

                    if (day.payments.length > 2) {
                        (function (dayRef) {
                            var more = document.createElement("div");
                            more.className = "pc-pill-more";
                            more.textContent = "+" + (dayRef.payments.length - 2) + " more";
                            more.addEventListener("click", function (e) {
                                e.stopPropagation();
                                self.show_day_detail(dayRef);
                            });
                            pills.appendChild(more);
                        })(day);
                    }

                    cell.appendChild(pills);
                }

                (function (dayRef) {
                    cell.addEventListener("click", function () {
                        if (dayRef.payments && dayRef.payments.length > 0) {
                            self.show_day_detail(dayRef);
                        }
                    });
                })(day);

                week_row.appendChild(cell);
            }

            days_container.appendChild(week_row);
        }
    }

    show_day_detail(day) {
        var self = this;
        var payments_html = day.payments.map(function (p) {
            return `
                <div class="pc-detail-row" data-name="${p.name}">
                    <div class="pc-detail-status">
                        <span class="pc-dot pc-dot-${p.status.toLowerCase()}"></span>
                    </div>
                    <div class="pc-detail-info">
                        <div class="pc-detail-vendor">${p.vendor}</div>
                        <div class="pc-detail-meta">${p.entity} · ${p.mode || ""} · ${p.status}</div>
                    </div>
                    <div class="pc-detail-amount">${self.fmt$(p.amount)}</div>
                </div>
            `;
        }).join("");

        var total = day.payments.reduce(function (sum, p) { return sum + p.amount; }, 0);
        var date_obj = new Date(day.date + "T00:00:00");
        var formatted_date = date_obj.toLocaleDateString("en-US", {
            weekday: "long", month: "long", day: "numeric", year: "numeric"
        });

        var dialog = new frappe.ui.Dialog({
            title: formatted_date,
            size: "large",
            fields: [{
                fieldtype: "HTML",
                fieldname: "detail_html",
                options: `
                    <div class="pc-detail-list">
                        ${payments_html}
                        <div class="pc-detail-total">
                            <span>Total</span>
                            <span>${self.fmt$(total)}</span>
                        </div>
                    </div>
                `
            }],
        });

        dialog.show();

        dialog.$wrapper.find(".pc-detail-row").on("click", function () {
            var name = $(this).data("name");
            if (name) {
                dialog.hide();
                frappe.set_route("Form", "Payment Entry", name);
            }
        });
    }

    go_prev() {
        if (this.current_month === 1) {
            this.current_month = 12;
            this.current_year--;
        } else {
            this.current_month--;
        }
        this.load_data();
    }

    go_next() {
        if (this.current_month === 12) {
            this.current_month = 1;
            this.current_year++;
        } else {
            this.current_month++;
        }
        this.load_data();
    }

    go_today() {
        var today = new Date();
        this.current_month = today.getMonth() + 1;
        this.current_year = today.getFullYear();
        this.load_data();
    }

    set_entity(entity) {
        this.entity = entity;
        this.load_data();
    }

    fmt$(val) {
        if (val == null || isNaN(val)) return "$0";
        var n = parseFloat(val);
        if (n === 0) return "$0";
        return "$" + n.toLocaleString("en-US", {
            minimumFractionDigits: n % 1 === 0 ? 0 : 2,
            maximumFractionDigits: 2,
        });
    }

    truncate(str, len) {
        if (!str) return "";
        return str.length > len ? str.substring(0, len) + "…" : str;
    }
}