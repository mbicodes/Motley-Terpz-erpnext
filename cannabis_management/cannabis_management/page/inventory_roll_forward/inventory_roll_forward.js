// Inventory Roll Forward -- opening, what came in, what went out, closing,
// for every month of a year, one company at a time. Pounds, grams and units
// are separate sections and never added together. All numbers come from
// cannabis_management.api.inventory_roll_forward.get_roll_forward; this file
// only renders.

frappe.pages["inventory-roll-forward"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Inventory Roll Forward"), single_column: true });
	new InventoryRollForward(page);
};

const IRF_API = "cannabis_management.api.inventory_roll_forward.";
const IRF_SIGN = { add: __("add"), less: __("less"), net: "±" };

class InventoryRollForward {
	constructor(page) {
		this.page = page;
		this.$root = $('<div class="irf"></div>').appendTo(page.main);
		this.make_filters();
		this.init();
	}

	make_filters() {
		const reload = () => this.refresh();
		this.company = this.page.add_field({
			fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, change: reload,
		});
		this.year = this.page.add_field({ fieldname: "year", label: __("Year"), fieldtype: "Select", change: reload });
		this.group_by = this.page.add_field({
			fieldname: "group_by", label: __("Show By"), fieldtype: "Select",
			options: [
				{ value: "Unit", label: __("Unit (Pounds / Grams / Units)") },
				{ value: "Item Group", label: __("Item Group") },
			],
			default: "Unit", change: reload,
		});
		this.item_group = this.page.add_field({
			fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group", change: reload,
		});
		this.page.set_secondary_action(__("Refresh"), reload, "refresh");
		this.page.add_inner_button(__("Download CSV"), () => this.download());
	}

	async init() {
		const { message: d } = await frappe.call(IRF_API + "get_filters");
		this.quiet = true;
		this.year.df.options = d.years;
		this.year.refresh();
		await this.year.set_value(d.year);
		if (d.company) await this.company.set_value(d.company);
		this.quiet = false;
		this.refresh();
	}

	async refresh() {
		if (this.quiet) return;
		const company = this.company.get_value();
		if (!company || !this.year.get_value()) {
			this.$root.html(`<div class="irf-empty">${__("Pick a company.")}</div>`);
			return;
		}
		this.$root.html(`<div class="irf-empty">${__("Loading…")}</div>`);
		const { message } = await frappe.call({
			method: IRF_API + "get_roll_forward",
			args: {
				company,
				year: this.year.get_value(),
				group_by: this.group_by.get_value(),
				item_group: this.item_group.get_value() || null,
			},
		});
		this.data = message;
		this.render();
	}

	render() {
		const d = this.data;
		if (!d.months.length) {
			this.$root.html(`<div class="irf-empty">${__("{0} has not started yet.", [d.year])}</div>`);
			return;
		}
		if (!d.sections.length) {
			this.$root.html(`<div class="irf-empty">${__("No stock movement for {0} in {1}.", [d.company, d.year])}</div>`);
			return;
		}
		const symbol = frappe.utils.escape_html(get_currency_symbol(d.currency) || d.currency || "");
		this.$root.html(
			`<div class="irf-note">${__(
				"Closing = Opening + Purchases + Yield / Receipts + Production − Issued to Production − Sales ± Loss / Adjustments ± Transfers. Quantities in each section's own unit, values in {0}.",
				[symbol]
			)}</div>` + d.sections.map((s) => this.section_html(s, symbol)).join("")
		);
	}

	section_html(s, symbol) {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		const rows = d.rows.filter((r) => !r.sign || s.active_rows.includes(r.key));
		const head1 = d.months.map((m) => `<th colspan="2" class="irf-month">${esc(__(m.label))}</th>`).join("");
		const head2 = d.months.map(() => `<th class="irf-q">${__("Qty")}</th><th class="irf-v">${__("Value")} (${symbol})</th>`).join("");
		const body = rows
			.map((r) => {
				const cells = s.months.map((m) => this.pair(m[r.key])).join("");
				return `<tr class="irf-row irf-${r.key} ${r.sign ? "irf-move" : "irf-balance"}">
					<td class="irf-sign">${r.sign ? IRF_SIGN[r.sign] : ""}</td>
					<td class="irf-label">${esc(r.label)}</td>${cells}${this.pair(s.year[r.key], true)}</tr>`;
			})
			.join("");
		const closing = s.year.closing;
		return `<div class="irf-section">
			<div class="irf-head">
				<div>
					<div class="irf-title">${esc(s.title)}</div>
					<div class="irf-groups">${esc(s.item_groups.join(", "))}</div>
				</div>
				<div class="irf-total">${__("Closing")}: <b>${this.qty(closing[0])}</b> · <b>${this.val(closing[1])}</b></div>
			</div>
			<div class="irf-scroll"><table class="irf-table">
				<thead>
					<tr><th class="irf-sign"></th><th class="irf-label"></th>${head1}<th colspan="2" class="irf-month irf-year">${esc(String(d.year))}</th></tr>
					<tr><th class="irf-sign"></th><th class="irf-label"></th>${head2}<th class="irf-q irf-year">${__("Qty")}</th><th class="irf-v irf-year">${__("Value")}</th></tr>
				</thead>
				<tbody>${body}</tbody>
			</table></div>
		</div>`;
	}

	pair(cell, year) {
		const [q, v] = cell || [0, 0];
		const cls = year ? " irf-year" : "";
		return `<td class="irf-q${cls}">${this.qty(q)}</td><td class="irf-v${cls}">${this.val(v)}</td>`;
	}

	qty(v) {
		return v ? format_number(v, null, 2) : '<span class="irf-zero">–</span>';
	}

	val(v) {
		return v ? format_number(v, null, 2) : '<span class="irf-zero">–</span>';
	}

	download() {
		const d = this.data;
		if (!d || !d.sections.length) return;
		const header = [__("Section"), __("Row")];
		d.months.forEach((m) => header.push(`${m.label} ${__("Qty")}`, `${m.label} ${__("Value")}`));
		header.push(`${d.year} ${__("Qty")}`, `${d.year} ${__("Value")}`);
		const out = [header];
		d.sections.forEach((s) => {
			d.rows
				.filter((r) => !r.sign || s.active_rows.includes(r.key))
				.forEach((r) => {
					const line = [s.title, (r.sign ? IRF_SIGN[r.sign] + " " : "") + r.label];
					s.months.forEach((m) => line.push(...m[r.key]));
					line.push(...s.year[r.key]);
					out.push(line);
				});
		});
		frappe.tools.downloadify(out, null, `Inventory Roll Forward - ${d.company} - ${d.year}`);
	}
}
