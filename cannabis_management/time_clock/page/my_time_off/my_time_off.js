// Employee dashboard: hours this pay period by day, PTO and Sick banks, upcoming time off, handbook.
frappe.pages["my-time-off"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("My Time Off"), single_column: true });
	page.set_primary_action(__("Request Time Off"), () => frappe.new_doc("Time Off Request"));
	if (frappe.user.has_role(["HR Manager", "HR User", "System Manager"]))
		page.add_inner_button(__("Team Calendar"), () => frappe.set_route("List", "Time Off Request", "Calendar"));
	page.add_inner_button(__("My Requests"), () => frappe.set_route("List", "Time Off Request"));
	$(`<style>
		.mto { display: grid; gap: 16px; padding-block: 8px 24px; }
		.mto-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
		.mto-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); padding: 14px 16px; display: grid; gap: 6px; align-content: start; }
		.mto-num { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.1; }
		.mto-num small { font-size: 13px; font-weight: 500; color: var(--text-muted); }
		.mto-muted { color: var(--text-muted); font-size: 12px; }
		.mto-meter { height: 6px; border-radius: 3px; background: var(--gray-200); overflow: hidden; }
		.mto-meter i { display: block; height: 100%; }
		.mto-main { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 12px; }
		@media (max-width: 768px) { .mto-main { grid-template-columns: 1fr; } }
		.mto-bars { display: grid; grid-template-columns: repeat(14, 1fr); gap: 4px; height: 160px; }
		.mto-bar { display: grid; grid-template-rows: auto 1fr auto; justify-items: center; gap: 2px; min-width: 0; }
		.mto-bar .col { width: 100%; align-self: end; border-radius: 3px 3px 0 0; background: var(--primary); }
		.mto-bar .col.off { background: var(--purple-100, #ede9fe); border: 1px dashed #7c3aed; }
		.mto-bar .col.today { outline: 2px solid var(--text-color); outline-offset: 1px; }
		.mto-bar span { font-size: 10px; color: var(--text-muted); text-align: center; font-variant-numeric: tabular-nums; }
		.mto-up { display: grid; gap: 8px; }
		.mto-up a { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; color: var(--text-color); }
	</style>`).appendTo(wrapper);
	this.body = $('<div class="mto"></div>').appendTo(page.main);
};

frappe.pages["my-time-off"].on_page_show = function () {
	const $b = this.body;
	frappe.call("cannabis_management.time_clock.time_off.my_dashboard").then(({ message: d }) => {
		const esc = frappe.utils.escape_html, fmt = (v) => frappe.datetime.str_to_user(v);
		const handbook = d.handbook
			? `<a class="btn btn-default btn-sm" href="${encodeURI(d.handbook)}" target="_blank" rel="noopener">${__("Open Employee Handbook")}</a>`
			: `<span class="mto-muted">${__("HR has not uploaded the handbook yet (Time Off Settings).")}</span>`;
		if (!d.employee) {
			$b.html(`<div class="mto-card"><b>${__("Your user is not linked to an Employee.")}</b>
				<span class="mto-muted">${__("Ask HR to set your user on your Employee record.")}</span>${handbook}</div>`);
			return;
		}
		const bank = (type, colour) => {
			const t = d.balances.types[type], pct = t.earned ? Math.max(0, Math.min(100, (t.available / t.earned) * 100)) : 0;
			return `<div class="mto-card"><span class="mto-muted">${__(type)} ${__("bank")}</span>
				<span class="mto-num">${t.available} <small>${__("hrs")}</small></span>
				<div class="mto-meter"><i style="width:${pct}%;background:${colour}"></i></div>
				<span class="mto-muted">${__("Earned {0} · used {1} · waiting {2} ({3})", [t.earned, t.used, t.pending, d.balances.year])}</span></div>`;
		};
		const total = d.days.reduce((s, x) => s + x.hours, 0);
		const max = Math.max(10, ...d.days.map((x) => x.hours));
		const isOff = (date) => d.off.some((r) => r.from_date <= date && date <= r.to_date);
		const bars = d.days.map((x) => {
			const off = !x.hours && isOff(x.date), h = off ? max * 0.5 : x.hours;
			const day = frappe.datetime.str_to_obj(x.date);
			return `<div class="mto-bar" title="${fmt(x.date)}: ${x.hours} ${__("hrs")}${off ? " · " + __("time off") : ""}">
				<span>${x.hours ? x.hours.toFixed(1) : off ? __("off") : ""}</span>
				<div class="col${off ? " off" : ""}${x.date === d.today ? " today" : ""}" style="height:${(h / max) * 100}%"></div>
				<span>${"SMTWTFS"[day.getDay()]}<br>${day.getDate()}</span></div>`;
		}).join("");
		const pill = { Pending: "orange", Approved: "green" };
		const upcoming = d.upcoming.length
			? d.upcoming.map((r) => `<a href="/app/time-off-request/${encodeURIComponent(r.name)}">
				<span>${fmt(r.from_date)}${r.to_date !== r.from_date ? " – " + fmt(r.to_date) : ""} · ${r.total_hours} ${__("hrs")}</span>
				<span class="indicator-pill ${pill[r.status]}">${__(r.leave_type)} · ${__(r.status)}</span></a>`).join("")
			: `<span class="mto-muted">${__("Nothing booked.")}</span>`;

		$b.html(`
			<div class="mto-muted">${esc(d.employee_name)} · ${esc(d.balances.category || __("No Time Off Category set"))} ·
				${__("Pay period {0} – {1}", [fmt(d.period[0]), fmt(d.period[1])])}</div>
			<div class="mto-cards">
				<div class="mto-card"><span class="mto-muted">${__("Hours this pay period")}</span>
					<span class="mto-num">${total.toFixed(2)} <small>${__("hrs")}</small></span>
					<span class="mto-muted">${__("From the time clock, through today")}</span></div>
				${bank("PTO", "#7c3aed")}${bank("Sick Time", "#ea580c")}
			</div>
			<div class="mto-main">
				<div class="mto-card"><b>${__("Hours worked by day")}</b><div class="mto-bars">${bars}</div>
					<span class="mto-muted">${__("Dashed bar = approved time off.")}</span></div>
				<div class="mto-card"><b>${__("Upcoming time off")}</b><div class="mto-up">${upcoming}</div></div>
			</div>
			<div class="mto-card" style="grid-template-columns: 1fr auto; align-items: center"><b>${__("Employee Handbook")}</b>${handbook}</div>`);
	});
};
