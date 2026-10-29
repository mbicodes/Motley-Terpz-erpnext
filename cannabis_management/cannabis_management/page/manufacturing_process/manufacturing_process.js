frappe.pages["manufacturing-process"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Manufacturing Process",
		single_column: true,
	});
	page.main.html('<div id="mfg-control-app"></div>');
	new ManufacturingRun(page);
};

class ManufacturingRun {
	constructor(page) {
		this.page = page;
		this.$app = page.main.find("#mfg-control-app");
		this.picker_data = null;
		this.runs = {};
		this.timer_interval = null;
		this.item_filter = null;
		this.project_filter = null;
		this.operation_filter = null;
		this.collapsed = new Set();
		this.toggled_by_hand = new Set();
		this.default_employee = null;
		this.date_filter = null;
		this.view = "list";
		try { if (localStorage.getItem("mc_view") === "calendar") this.view = "calendar"; } catch (e) {  }
		this.load_picker();
		this._start_live_sync();
	}

	api(method, args) {
		return frappe.xcall("cannabis_management.api.manufacturing_process." + method, args);
	}

	async load_picker() {
		this._stop_ticks();
		this.runs = {};
		this.$app.html('<div class="mc-loading">Loading…</div>');

		try {
			this.picker_data = await this.api("get_dashboard");
			this.render_picker();
		} catch (e) {
			this.$app.html(`<div class="mc-empty">Error loading runs: ${esc(e.message || e)}</div>`);
		}
	}

	render_picker() {
		const d = this.picker_data;
		const filtered = this._get_filtered_mrs();
		const html = `
		<div class="mc-header">
			<h1 id="mc-active-runs-heading">Active Runs - ${filtered.length}</h1>
			<div class="mc-header-actions">
				<div class="mc-filter-wrap" id="mc-item-filter-wrap"></div>
				<div class="mc-filter-wrap" id="mc-project-filter-wrap"></div>
				<div class="mc-filter-wrap" id="mc-operation-filter-wrap"></div>
				<select class="mc-wo-search" id="mc-view-select" title="View">
					<option value="list"${this.view === "list" ? " selected" : ""}>List View</option>
					<option value="calendar"${this.view === "calendar" ? " selected" : ""}>Calendar View</option>
				</select>
				<input type="date" class="mc-wo-search" id="mc-date-filter" title="Filter by Date" value="${this.date_filter ? esc(this.date_filter) : ""}">
				<button class="mc-btn mc-btn-secondary" data-action="clear_filters" title="Clear the Item, Project, Operation and Date filters"><i class="ti ti-filter-off" aria-hidden="true"></i> Clear Filters</button>
				<button class="mc-btn mc-btn-secondary" data-action="collapse_all">Collapse All</button>
				<button class="mc-btn mc-btn-secondary" data-action="expand_all">Expand All</button>
				<button class="mc-btn mc-btn-dashboard" data-action="open_dashboard" title="Open the Manufacturing Dashboard"><i class="ti ti-layout-dashboard" aria-hidden="true"></i> Switch to Dashboard</button>
				<button class="mc-btn mc-btn-primary" data-action="new_run">+ New Run</button>
				<button class="mc-btn mc-btn-secondary" data-action="refresh">↻ Refresh</button>
			</div>
		</div>
		<div class="mc-section">
			<div class="mc-run-groups">${this._render_run_card_shells(filtered)}</div>
			<div class="mc-calendar"></div>
		</div>`;

		this.$app.html(html);
		this._cal_ready = false;
		this._observe_card_heights();
		this._bind_picker_events();
		this._load_all_run_details(filtered);
		this._show_view();
	}

	_show_view() {
		const calendar = this.view === "calendar";
		this.$app.find(".mc-run-groups").toggle(!calendar);
		this.$app.find(".mc-calendar").toggle(calendar);
		this.$app.find('[data-action="collapse_all"], [data-action="expand_all"]').toggle(!calendar);
		if (calendar) this._render_calendar();
	}

	async _render_calendar() {
		const $cal = this.$app.find(".mc-calendar");
		if (!this._cal_ready) {
			await frappe.require([
				"assets/frappe/js/lib/fullcalendar/fullcalendar.min.css",
				"assets/frappe/js/lib/fullcalendar/fullcalendar.min.js",
			]);
			$cal.fullCalendar({
				header: { left: "prev,next today", center: "title", right: "month,basicWeek,listMonth" },
				defaultView: "month",
				height: "auto",
				eventLimit: 4,
				events: (start, end, tz, callback) => callback(this._calendar_events()),
				eventClick: (event) => this._open_run_from_calendar(event.id),
				eventRender: (event, $el) => { $el.attr("title", event.tooltip); },
			});
			this._cal_ready = true;
		} else {
			$cal.fullCalendar("refetchEvents");
		}
	}

	_calendar_events() {
		const COLORS = {
			"Draft": "#6c757d", "Pending": "#7b2fbf", "In Progress": "#fd7e14", "Completed": "#28a745",
		};
		return this._get_filtered_mrs().filter(m => m.transaction_date).map(m => {
			const { status_label } = this._run_status_badge(m.docstatus, m.status);
			const batch = m.project_name || "No Batch";
			return {
				id: m.name,
				title: `${m.primary_label}${m.output_label ? ` → ${m.output_label}` : ""} · ${batch}`,
				start: m.transaction_date,
				allDay: true,
				color: COLORS[status_label] || "#007bff",
				tooltip: `${m.primary_label}${m.output_label ? `\n→ ${m.output_label}` : ""}\n${batch} · ${status_label}\n${m.primary_qty || ""}\n${m.name}`,
			};
		});
	}

	_open_run_from_calendar(mr_name) {
		this.view = "list";
		try { localStorage.setItem("mc_view", "list"); } catch (e) {  }
		this.$app.find("#mc-view-select").val("list");
		this._show_view();
		const $card = this.$app.find(`.mc-run-card[data-mr="${mr_name}"]`);
		if (!$card.length) return;
		if ($card.hasClass("is-collapsed")) {
			this.toggled_by_hand.add(mr_name);
			this.collapsed.delete(mr_name);
			this._set_card_collapsed($card, false);
		}
		$card[0].scrollIntoView({ behavior: "smooth", block: "start" });
		$card.addClass("mc-card-flash");
		setTimeout(() => $card.removeClass("mc-card-flash"), 2000);
	}

	_get_filtered_mrs() {
		const mrs = (this.picker_data && this.picker_data.material_requests) || [];
		return mrs.filter(m => {
			if (this.item_filter) {
				const matches_item = (m.items || []).some(i => i.item_code === this.item_filter)
					|| (m.finished_goods || []).some(fg => fg.item === this.item_filter);
				if (!matches_item) return false;
			}
			if (this.project_filter && m.custom_project !== this.project_filter) return false;
			if (this.operation_filter) {
				const matches_op = (m.finished_goods || []).some(fg => fg.operation === this.operation_filter);
				if (!matches_op) return false;
			}
			if (this.date_filter && m.transaction_date !== this.date_filter) return false;
			return true;
		});
	}

	_apply_filters() {
		const filtered = this._get_filtered_mrs();
		this.$app.find("#mc-active-runs-heading").text(`Active Runs - ${filtered.length}`);
		this.$app.find(".mc-run-groups").html(this._render_run_card_shells(filtered));
		this._observe_card_heights();
		this._load_all_run_details(filtered);
		if (this.view === "calendar") this._render_calendar();
	}

	_render_run_card_shells(mrs) {
		if (!mrs.length) return '<div class="mc-empty">No active runs — start one to get going.</div>';
		const groups = new Map();
		mrs.forEach(m => {
			const key = m.custom_project || "";
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key).push(m);
		});
		const latest = (runs) => runs.reduce((d, m) => (m.transaction_date || "") > d ? m.transaction_date : d, "");
		return [...groups.values()]
			.map(runs => runs.slice().sort((a, b) => (b.transaction_date || "").localeCompare(a.transaction_date || "")))
			.sort((a, b) => {
				if (!a[0].custom_project !== !b[0].custom_project) return a[0].custom_project ? -1 : 1;
				return (b[0].project_name || "").localeCompare(a[0].project_name || "", undefined, { numeric: true })
					|| latest(b).localeCompare(latest(a));
			})
			.map(runs => {
				const dates = runs.map(m => m.transaction_date).filter(Boolean).sort();
				const range = !dates.length ? ""
					: dates[0] === dates[dates.length - 1] ? this._fmt_date(dates[0])
					: `${this._fmt_date(dates[0])} – ${this._fmt_date(dates[dates.length - 1])}`;
				return `
				<div class="mc-batch-group">
					<div class="mc-batch-head">
						<span class="mc-batch-name">Batch: ${esc(runs[0].project_name || "No Batch")}</span>
						<span class="mc-muted">${runs.length} run${runs.length === 1 ? "" : "s"}${range ? ` · ${esc(range)}` : ""}</span>
					</div>
					<div class="mc-run-list">${runs.map(m => this._render_run_card_shell(m)).join("")}</div>
				</div>`;
			}).join("");
	}

	_fmt_date(d) {
		return d ? frappe.datetime.str_to_user(d) : "";
	}

	_render_run_card_shell(m) {
		const { status_class, status_label } = this._run_status_badge(m.docstatus, m.status);
		const collapsed = this.collapsed.has(m.name);
		return `
		<div class="mc-run-card${collapsed ? " is-collapsed" : ""}" data-mr="${esc(m.name)}">
			<div class="mc-ops-card-head">
				<button class="mc-card-toggle" data-action="toggle_card" title="${collapsed ? "Expand" : "Collapse"}" aria-expanded="${collapsed ? "false" : "true"}">${collapsed ? "▸" : "▾"}</button>
				<div class="mc-ops-card-info">
					<div class="mc-run-card-title">${esc(m.primary_label)}${m.output_label ? `<span class="mc-run-card-output" title="Output"> → ${esc(m.output_label)}</span>` : ""}</div>
					<div class="mc-run-meta">
						<span title="Transaction Date"><i class="ti ti-calendar" aria-hidden="true"></i> ${esc(this._fmt_date(m.transaction_date) || "—")}</span>
						<span>${esc(m.primary_qty)} <a class="mc-open-desk-link" onclick="frappe.set_route('Form','Material Request','${esc(m.name)}')">Open in Desk</a></span>
						<span class="mc-status mc-status-${status_class}" data-role="run-status">${status_label}</span>
					</div>
				</div>
				<div class="mc-ops-card-actions">${this._render_attach_action()}${this._render_release_action(m.work_order_count > 0)}</div>
			</div>
			<div class="mc-run-card-body"><div class="mc-loading" style="padding:20px 0;">Loading operations…</div></div>
		</div>`;
	}

	_run_status_badge(docstatus, status) {
		const status_label = docstatus === 0 ? "Draft" : (status || "Submitted");
		const status_class = status_label.toLowerCase().replace(/\s+/g, "-");
		return { status_class, status_label };
	}

	_run_stage_badge(run, tiering_pending) {
		const mr = run.material_request;
		if (mr.docstatus !== 1 || !run.work_orders.length || ["Stopped", "Cancelled"].includes(mr.status)) {
			return this._run_status_badge(mr.docstatus, mr.status);
		}
		const active_wo = run.work_orders.find(w => w.name === run.active_work_order);
		if (active_wo) return { status_class: "in-progress", status_label: `Waiting for ${this._stage_name(active_wo)}` };
		if (tiering_pending) return { status_class: "tiering-required", status_label: "Waiting for Tiering" };
		return { status_class: "completed", status_label: "Completed" };
	}

	_stage_name(wo) {
		const STAGE_NAMES = { "Hash Processing": "Bubble Hash", "Rosin Pressing": "Rosin" };
		const op = ((wo.job_cards || [])[0] || {}).operation;
		if (STAGE_NAMES[op]) return STAGE_NAMES[op];
		const item = wo.item_name || wo.production_item || "";
		return item.split(/\s*-\s*/).pop() || op || item;
	}

	_observe_card_heights() {
		if (this._card_observer) this._card_observer.disconnect();
		const list = this.$app.find(".mc-run-list")[0];
		if (!list || typeof ResizeObserver === "undefined") return;
		const row = parseFloat(getComputedStyle(list).gridAutoRows) || 8;
		const gap = parseFloat(getComputedStyle(list).rowGap) || 0;
		const GUTTER = 16;
		this._card_observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const card = entry.target;
				const span = Math.ceil((card.getBoundingClientRect().height + GUTTER + gap) / (row + gap));
				card.style.gridRowEnd = `span ${span}`;
			}
		});
		this.$app[0].querySelectorAll(".mc-run-list .mc-run-card").forEach((card) => this._card_observer.observe(card));
	}

	_render_release_action(released) {
		return released
			? `<span class="mc-btn mc-btn-sm mc-step-done">Released</span>`
			: `<button class="mc-btn mc-btn-sm mc-btn-pending" data-action="release_run">Release</button>`;
	}

	_render_print_log_action(run) {
		const rosin_done = run.work_orders.some(wo => wo.manufacture_entry
			&& (wo.job_cards || []).some(jc => jc.operation === "Rosin Pressing"));
		return rosin_done
			? `<button class="mc-btn mc-btn-sm mc-btn-secondary" data-action="print_log" title="Print this run's Production Log for the log book"><i class="ti ti-printer" aria-hidden="true"></i> Print Log</button>`
			: "";
	}

	_render_attach_action(files) {
		const n = (files || []).length;
		return n
			? `<button class="mc-btn mc-btn-sm mc-btn-secondary" data-action="attachments" title="See what is attached to this run"><i class="ti ti-paperclip" aria-hidden="true"></i> Attachments (${n})</button>`
			: `<button class="mc-btn mc-btn-sm mc-btn-secondary" data-action="attachments" title="Attach files to the Material Request"><i class="ti ti-paperclip" aria-hidden="true"></i> Attach</button>`;
	}

	_set_attachments(mr_name, files) {
		if (this.runs[mr_name]) this.runs[mr_name].attachments = files;
		this.$app.find(`.mc-run-card[data-mr="${mr_name}"] [data-action="attachments"]`)
			.replaceWith(this._render_attach_action(files));
	}

	async _upload_attachments(mr_name, on_added) {
		await frappe.require("file_uploader.bundle.js");
		let queue = Promise.resolve();
		new frappe.ui.FileUploader({
			doctype: "Material Request",
			docname: mr_name,
			folder: "Home/Attachments",
			allow_multiple: true,
			on_success: (file) => {
				queue = queue.then(async () => {
					try {
						const files = await this.api("add_attachment", { material_request: mr_name, file_url: file.file_url });
						this._set_attachments(mr_name, files);
						frappe.show_alert({ message: `${esc(file.file_name || "File")} attached to ${esc(mr_name)}`, indicator: "green" });
						if (on_added) on_added();
					} catch (e) { frappe.msgprint(e.message || e); }
				});
			},
		});
	}

	_open_attachments_dialog(mr_name) {
		const files = () => (this.runs[mr_name] && this.runs[mr_name].attachments) || [];
		const d = new frappe.ui.Dialog({
			title: `Attachments — ${mr_name}`,
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "files" }],
			primary_action_label: "Add Files",
			primary_action: () => this._upload_attachments(mr_name, render),
		});
		const $files = d.fields_dict.files.$wrapper;
		const render = () => {
			const list = files();
			d.set_title(`Attachments — ${mr_name} (${list.length})`);
			$files.html(list.length
				? `<div class="mc-att-grid">${list.map(f => this._render_attachment_tile(f)).join("")}</div>`
				: '<div class="mc-att-empty">No files attached yet — use Add Files.</div>');
		};
		$files.on("click", "[data-att-view]", (e) => {
			const f = files().find(x => x.name === $(e.currentTarget).attr("data-att-view"));
			if (f) this._preview_attachment(f);
		});
		$files.on("click", "[data-att-remove]", (e) => {
			const f = files().find(x => x.name === $(e.currentTarget).attr("data-att-remove"));
			if (!f) return;
			frappe.confirm(`Remove <b>${esc(this._file_name(f.attachment))}</b> from ${esc(mr_name)}?`, async () => {
				try {
					const list = await this.api("remove_attachment", { material_request: mr_name, row: f.name });
					this._set_attachments(mr_name, list);
					frappe.show_alert({ message: "Attachment removed", indicator: "orange" });
					render();
				} catch (err) { frappe.msgprint(err.message || err); }
			});
		});
		render();
		d.show();
	}

	_render_attachment_tile(f) {
		const url = f.attachment;
		const name = this._file_name(url);
		const kind = this._file_kind(url);
		let thumb;
		if (kind === "image") thumb = `<img src="${esc(url)}" alt="" loading="lazy">`;
		else if (kind === "pdf") thumb = `<iframe src="${esc(url)}#toolbar=0&navpanes=0&view=FitH" tabindex="-1" loading="lazy" title="${esc(name)}"></iframe>`;
		else if (kind === "video") thumb = `<video src="${esc(url)}" preload="metadata" muted></video>`;
		else thumb = `<i class="ti ${this._file_icon(url)}" aria-hidden="true"></i><span class="mc-att-ext">${esc(this._file_ext(url) || "file")}</span>`;
		return `
		<div class="mc-att-tile">
			<button class="mc-att-thumb" data-att-view="${esc(f.name)}" title="Preview ${esc(name)}">${thumb}</button>
			<div class="mc-att-info">
				<div class="mc-att-name" title="${esc(name)}">${esc(name)}</div>
				<div class="mc-att-meta">${esc(this._attachment_meta(f))}</div>
			</div>
			<div class="mc-att-actions">
				<button class="btn btn-xs btn-default" data-att-view="${esc(f.name)}"><i class="ti ti-eye" aria-hidden="true"></i> View</button>
				<a class="btn btn-xs btn-default" href="${esc(url)}" target="_blank" rel="noopener"><i class="ti ti-external-link" aria-hidden="true"></i> Open</a>
				<button class="btn btn-xs btn-default mc-att-remove" data-att-remove="${esc(f.name)}" title="Remove"><i class="ti ti-trash" aria-hidden="true"></i></button>
			</div>
		</div>`;
	}

	_preview_attachment(f) {
		const url = f.attachment;
		const kind = this._file_kind(url);
		let body;
		if (kind === "image") body = `<img class="mc-att-full" src="${esc(url)}" alt="">`;
		else if (kind === "pdf" || kind === "text") body = `<iframe class="mc-att-frame" src="${esc(url)}"></iframe>`;
		else if (kind === "video") body = `<video class="mc-att-full" src="${esc(url)}" controls></video>`;
		else body = `<div class="mc-att-empty"><i class="ti ${this._file_icon(url)}" aria-hidden="true"></i><br>No preview for .${esc(this._file_ext(url))} files — use Open to download it.</div>`;
		const d = new frappe.ui.Dialog({
			title: this._file_name(url),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", options: `${body}<div class="mc-att-meta mc-att-full-meta">${esc(this._attachment_meta(f))}</div>` }],
			primary_action_label: "Open in New Tab",
			primary_action: () => window.open(url, "_blank", "noopener"),
		});
		d.show();
	}

	_attachment_meta(f) {
		return [f.uploaded_by_name, f.uploaded_on ? frappe.datetime.str_to_user(f.uploaded_on) : ""].filter(Boolean).join(" · ");
	}

	_file_name(url) {
		return (url || "").split("?")[0].split("/").pop() || url;
	}

	_file_ext(url) {
		const name = this._file_name(url);
		return name.includes(".") ? name.split(".").pop().toLowerCase() : "";
	}

	_file_kind(url) {
		const ext = this._file_ext(url);
		if (["png", "jpg", "jpeg", "gif", "webp", "bmp"].includes(ext)) return "image";
		if (ext === "pdf") return "pdf";
		if (["mp4", "webm", "mov", "ogg"].includes(ext)) return "video";
		if (ext === "txt") return "text";
		return "other";
	}

	_file_icon(url) {
		const ext = this._file_ext(url);
		if (["xls", "xlsx", "csv", "ods"].includes(ext)) return "ti-file-spreadsheet";
		if (["pdf", "doc", "docx", "txt", "odt", "rtf"].includes(ext)) return "ti-file-text";
		return "ti-file";
	}

	async _load_all_run_details(mrs) {
		const queue = [];
		mrs.forEach((m) => {
			if (this.runs[m.name]) this._render_run_card_body(m.name);
			else queue.push(m);
		});
		const load_next = async () => {
			for (let m = queue.shift(); m; m = queue.shift()) {
				try {
					const run = await this.api("get_run_detail", { material_request: m.name });
					this.runs[m.name] = run;
					this._render_run_card_body(m.name);
				} catch (e) {
					this.$app.find(`.mc-run-card[data-mr="${m.name}"] .mc-run-card-body`)
						.html(`<div class="mc-empty">Error: ${esc(e.message || e)}</div>`);
				}
			}
		};
		await Promise.all(Array.from({ length: 6 }, load_next));
	}

	async _refresh_one(mr_name, { quiet = false } = {}) {
		try {
			const run = await this.api("get_run_detail", { material_request: mr_name });
			this.runs[mr_name] = run;
			this._render_run_card_body(mr_name);
		} catch (e) {
			if (!quiet) frappe.msgprint(e.message || e);
		}
	}

	_render_run_card_body(mr_name) {
		const run = this.runs[mr_name];
		if (!run) return;
		const active_wo = run.work_orders.find(w => w.name === run.active_work_order);
		const $card = this.$app.find(`.mc-run-card[data-mr="${mr_name}"]`);

		let body = this._render_ops_body(run, active_wo);
		const typing = this._note_being_typed($card);
		$card.find(".mc-run-card-body").html(body);
		if (typing) this._restore_note(typing);
		$card.find(".mc-ops-card-actions").html(
			this._render_attach_action(run.attachments) + this._render_release_action(run.work_orders.length > 0)
			+ this._render_print_log_action(run));
		const tiering_pending = run.work_orders.some(wo =>
			(wo.job_cards || []).some(jc => jc.operation === "Rosin Pressing") && !wo.tiering_entry);
		const badge = this._run_stage_badge(run, tiering_pending);
		$card.find('[data-role="run-status"]')
			.attr("class", `mc-status mc-status-${badge.status_class}`)
			.text(badge.status_label);
		if (run.complete && !tiering_pending && !this.toggled_by_hand.has(mr_name)) {
			this.collapsed.add(mr_name);
			this._set_card_collapsed($card, true);
		}

		this._start_ticks();
	}

	_note_being_typed($card) {
		const el = $card.find(".mc-sub-op-note:focus")[0];
		if (!el) return null;
		return { jc: el.getAttribute("data-jc"), op: el.getAttribute("data-op"), value: el.value,
			start: el.selectionStart, end: el.selectionEnd };
	}

	_restore_note(typing) {
		const el = this.$app.find(".mc-sub-op-note").toArray()
			.find(n => n.getAttribute("data-jc") === typing.jc && n.getAttribute("data-op") === typing.op);
		if (!el) return;
		el.value = typing.value;
		el.focus();
		try { el.setSelectionRange(typing.start, typing.end); } catch (e) {  }
	}

	_clear_filters() {
		this.item_filter = this.project_filter = this.operation_filter = this.date_filter = null;
		[this.item_filter_control, this.project_filter_control, this.operation_filter_control]
			.forEach(c => c && c.set_value(""));
		this.$app.find("#mc-date-filter").val("");
		this._apply_filters();
	}

	_bind_picker_events() {
		const self = this;
		const $app = this.$app;

		$app.off("click");

		$app.find('[data-action="new_run"]').click(() => self.show_new_mr_modal());
		$app.find('[data-action="open_dashboard"]').click(() => frappe.set_route("manufacturing-runs"));
		$app.find('[data-action="refresh"]').click(() => self.load_picker());

		this.item_filter_control = this._make_filter_control("#mc-item-filter-wrap", "Item", "item_filter", "Filter by Item");
		this.project_filter_control = this._make_filter_control("#mc-project-filter-wrap", "Project", "project_filter", "Filter by Project");

		$app.find('[data-action="collapse_all"]').click(() => {
			self._get_filtered_mrs().forEach(m => { self.collapsed.add(m.name); self.toggled_by_hand.add(m.name); });
			$app.find(".mc-run-card").each(function () { self._set_card_collapsed($(this), true); });
		});
		$app.find('[data-action="expand_all"]').click(() => {
			self.collapsed.clear();
			self._get_filtered_mrs().forEach(m => self.toggled_by_hand.add(m.name));
			$app.find(".mc-run-card").each(function () { self._set_card_collapsed($(this), false); });
		});
		$app.on("click", '[data-action="toggle_card"]', function () {
			const $card = $(this).closest(".mc-run-card");
			const mr_name = $card.data("mr");
			const collapse = !self.collapsed.has(mr_name);
			if (collapse) self.collapsed.add(mr_name); else self.collapsed.delete(mr_name);
			self.toggled_by_hand.add(mr_name);
			self._set_card_collapsed($card, collapse);
		});

		this.operation_filter_control = this._make_filter_control("#mc-operation-filter-wrap", "Operation", "operation_filter", "Filter by Operation");

		$app.find("#mc-view-select").on("change", function () {
			self.view = $(this).val() === "calendar" ? "calendar" : "list";
			try { localStorage.setItem("mc_view", self.view); } catch (e) {  }
			self._show_view();
		});
		$app.find("#mc-date-filter").on("change", function () {
			self.date_filter = $(this).val() || null;
			self._apply_filters();
		});
		$app.find('[data-action="clear_filters"]').click(() => self._clear_filters());

		$app.on("click", '[data-action="release_run"]', async function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			$btn.prop("disabled", true).text("Releasing…");
			try {
				frappe.show_alert({ message: "Creating Work Orders & Job Cards…", indicator: "blue" });
				const result = await self.api("create_work_orders", { material_request: mr_name });
				frappe.show_alert({
					message: `Released — ${(result.work_orders || []).length} stage(s) ready`,
					indicator: "green",
				});
				await self._refresh_one(mr_name);
			} catch (e) {
				frappe.msgprint(e.message || e);
				$btn.prop("disabled", false).text("Release");
			}
		});

		$app.on("click", '[data-action="attachments"]', function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const files = (self.runs[mr_name] && self.runs[mr_name].attachments) || [];
			if (files.length) self._open_attachments_dialog(mr_name);
			else self._upload_attachments(mr_name);
		});

		$app.on("click", '[data-action="print_log"]', function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const params = new URLSearchParams({
				doctype: "Material Request", name: mr_name, format: "Run Production Log",
				no_letterhead: 1, trigger_print: 1,
			});
			window.open(`/printview?${params}`, "_blank");
		});

		$app.off(".mcnote");
		$app.on("keydown.mcnote", ".mc-sub-op-note", function (e) {
			if (e.key === "Enter") { e.preventDefault(); this.blur(); }
		});
		$app.on("focusout.mcnote", ".mc-sub-op-note", function () {
			self._save_note($(this));
		});

		$app.on("click", '[data-action="transfer_run"]', function () {
			const $btn = $(this);
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const wo_name = $btn.attr("data-wo");
			if (!wo_name) {
				frappe.msgprint("No active Work Order yet — click Release first.");
				return;
			}
			self.show_transfer_modal(wo_name, mr_name);
		});

		$app.on("click", '[data-action="refresh_run"]', function () {
			self._refresh_one($(this).closest(".mc-run-card").data("mr"));
		});

		$app.on("click", '[data-action="start_sub_op"]', function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const original_label = $btn.text();
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const jc_name = $btn.data("jc");
			const operation = $btn.data("op");
			const jc = self.find_job_card(jc_name);
			const so = jc && (jc.sub_operations || []).find(s => s.operation === operation);
			self._ask_start(`${original_label} — ${operation}`, jc, so, async (v) => {
				$btn.prop("disabled", true).text("Starting…");
				try {
					await self.api("start_timer", { job_card: jc_name, operation, from_time: v.from_time, employee: v.employee, workstation: v.workstation });
					frappe.show_alert({ message: `Started — ${esc(operation)}`, indicator: "green" });
					await self._refresh_one(mr_name);
				} catch (e) {
					frappe.msgprint(e.message || e);
					$btn.prop("disabled", false).text(original_label);
				}
			});
		});

		$app.on("click", '[data-action="stop_sub_op"]', async function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const operation = $btn.data("op");
			$btn.prop("disabled", true).text("Pausing…");
			try {
				await self.api("pause_timer", { job_card: $btn.data("jc"), operation });
				frappe.show_alert({ message: `Paused — ${esc(operation)}`, indicator: "orange" });
				await self._refresh_one(mr_name);
			} catch (e) {
				frappe.msgprint(e.message || e);
				$btn.prop("disabled", false).text("Pause");
			}
		});

		$app.on("click", '[data-action="end_sub_op"]', function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const jc_name = $btn.data("jc");
			const operation = $btn.data("op");
			const jc = self.find_job_card(jc_name);
			const running_so = jc && (jc.sub_operations || []).find(s => s.operation === operation);
			const is_running = running_so ? running_so.status === "active"
				: !!(jc && jc.active_timer && jc.active_timer.operation === operation);
			const finish = async (v) => {
				$btn.prop("disabled", true).text("Ending…");
				try {
					await self.api("end_sub_operation", {
						job_card: jc_name,
						operation,
						to_time: v.to_time || null,
					});
					frappe.show_alert({ message: `Ended — ${esc(operation)}`, indicator: "blue" });
					await self._refresh_one(mr_name);
				} catch (e) {
					frappe.msgprint(e.message || e);
				} finally {
					$btn.prop("disabled", false).text("End");
				}
			};

			if (!is_running) {
				finish({});
				return;
			}
			const d = new frappe.ui.Dialog({
				title: `End — ${operation}`,
				fields: [
					{ fieldtype: "Datetime", fieldname: "to_time", label: "End Time", default: frappe.datetime.now_datetime(), reqd: 1 },
				],
				primary_action_label: "Confirm",
				primary_action: (v) => {
					d.hide();
					finish(v);
				},
			});
			d.show();
		});

		$app.on("click", '[data-action="view_sub_op"]', function () {
			const jc_name = $(this).data("jc");
			const operation = $(this).data("op");
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const jc = self.find_job_card(jc_name);
			if (!jc) return;
			const so = (jc.sub_operations || []).find(s => s.operation === operation);
			if (!so) return;
			self._open_view_time_modal(jc, so, mr_name);
		});

		$app.on("click", '[data-action="assign_sub_op"]', function () {
			const $btn = $(this);
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const jc_name = $btn.data("jc");
			const operation = $btn.data("op") || null;
			const jc = self.find_job_card(jc_name);
			const so = operation && jc && (jc.sub_operations || []).find(s => s.operation === operation);
			const current = (so ? so.assigned_employee : jc && jc.assigned_employee) || "";
			const save = async (employee) => {
				try {
					const r = await self.api("assign_employee", { job_card: jc_name, operation, employee });
					frappe.show_alert({
						message: r.employee ? `Assigned to ${esc(r.employee_name)}` : "Assignment removed",
						indicator: "green",
					});
					await self._refresh_one(mr_name);
				} catch (e) {
					frappe.msgprint(e.message || e);
				}
			};
			const d = new frappe.ui.Dialog({
				title: `Assign To — ${operation || (jc ? jc.operation : "")}`,
				fields: [
					{ fieldtype: "Link", fieldname: "employee", label: "Employee", options: "Employee", default: current, reqd: 1,
						get_query: () => ({ filters: { status: "Active" } }) },
				],
				primary_action_label: "Assign",
				primary_action: (v) => { d.hide(); save(v.employee); },
				...(current ? { secondary_action_label: "Remove", secondary_action: () => { d.hide(); save(null); } } : {}),
			});
			d.show();
		});

		$app.on("click", '[data-action="start_timer"]', function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const jc_name = $btn.data("jc");
			const jc = self.find_job_card(jc_name);
			self._ask_start(`Start — ${jc ? jc.operation : ""}`, jc, null, async (v) => {
				$btn.prop("disabled", true).text("Starting…");
				try {
					await self.api("start_timer", { job_card: jc_name, from_time: v.from_time, employee: v.employee, workstation: v.workstation });
					frappe.show_alert({ message: "Timer started", indicator: "green" });
					await self._refresh_one(mr_name);
				} catch (e) {
					frappe.msgprint(e.message || e);
					$btn.prop("disabled", false).text("▶ Start");
				}
			});
		});

		$app.on("click", '[data-action="pause_timer"]', async function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			$btn.prop("disabled", true).text("Pausing…");
			try {
				await self.api("pause_timer", { job_card: $btn.data("jc") });
				frappe.show_alert({ message: "Timer paused", indicator: "orange" });
				await self._refresh_one(mr_name);
			} catch (e) {
				frappe.msgprint(e.message || e);
				$btn.prop("disabled", false).text("⏸ Pause");
			}
		});

		$app.on("click", '[data-action="enter_microns"]', function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const jc = self.find_job_card($(this).data("jc"));
			if (!jc) return;
			self._open_micron_modal(jc, mr_name);
		});

		$app.on("click", '[data-action="create_sku"]', async function () {
			const $btn = $(this);
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const wo_name = $btn.data("wo");
			const jc = self.find_job_card($btn.data("jc"));
			if (!wo_name || !jc) return;
			const label = self._sku_button_label(jc.operation);

			if (jc.status === "Completed") {
				try {
					const preview = await self.api("get_manufacture_se_preview", { work_order: wo_name });
					self._show_sku_modal(preview, wo_name, mr_name);
				} catch (e) { frappe.msgprint(e.message || e); }
				return;
			}

			const micron_grams = (jc.micron_rows || []).reduce((t, r) => t + flt(r.grams_collected), 0);
			const from_microns = ["Hash Processing", "Rosin Pressing"].includes(jc.operation);
			if (from_microns && !micron_grams) {
				frappe.msgprint(`Enter the Microns for ${esc(jc.operation)} first — ${esc(label)} takes its output from them.`);
				return;
			}
			const d = new frappe.ui.Dialog({
				title: `${label} — ${jc.operation}`,
				fields: [
					{ fieldtype: "Float", fieldname: "completed_qty", label: "Output Qty (grams)", reqd: 1,
						read_only: from_microns ? 1 : 0,
						default: from_microns ? micron_grams : (micron_grams || flt(jc.for_quantity)),
						description: from_microns ? "Total of the Microns." : "" },
					{
						fieldtype: "Datetime",
						fieldname: "posting_datetime",
						label: "Completed Date & Time",
						reqd: 1,
						default: frappe.datetime.now_datetime(),
						description: "When the run actually finished. The stock entry posts at this time.",
					},
					{ fieldtype: "HTML", options: '<p style="color:var(--mc-gray);font-size:13px;">This finishes the operation and records the output as a Manufacture stock entry.</p>' },
				],
				primary_action_label: label,
				primary_action: async (v) => {
					d.hide();
					try {
						frappe.show_alert({ message: `${esc(label)}…`, indicator: "blue" });
						const result = await self.api("complete_job_card", {
							job_card: jc.name,
							completed_qty: v.completed_qty,
							posting_datetime: v.posting_datetime,
						});
						const se = result.stock_entry || {};
						if (se.submitted) {
							frappe.show_alert({ message: esc(self._output_done_label(jc.operation)), indicator: "green" });
						} else if (se.reason) {
							frappe.msgprint(esc(se.reason));
						}
						await self._refresh_one(mr_name);
					} catch (e) { frappe.msgprint(e.message || e); }
				},
			});
			d.show();
		});

		$app.on("click", '[data-action="view_output"]', async function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const wo_name = $(this).data("wo");
			if (!wo_name) return;
			try {
				const preview = await self.api("get_manufacture_se_preview", { work_order: wo_name });
				self._show_sku_modal(preview, wo_name, mr_name);
			} catch (e) { frappe.msgprint(e.message || e); }
		});

		$app.on("click", '[data-action="tiering_product"]', async function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const wo_name = $(this).data("wo");
			if (!wo_name) return;
			try {
				const doc = await self.api("make_tiering_conversion_entry", { work_order: wo_name });
				await new Promise(resolve => frappe.model.with_doctype("Conversion Entry Item", resolve));
				self._open_tiering_dialog(wo_name, doc, mr_name);
			} catch (e) { frappe.msgprint(e.message || e); }
		});
	}

	show_new_mr_modal() {
		const self = this;
		const new_row_name = () => frappe.utils.get_random(10);
		const d = new frappe.ui.Dialog({
			title: "Start a Run",
			size: "extra-large",
			fields: [
				{ fieldtype: "Link", fieldname: "company", label: "Company", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
				{
					fieldtype: "Link", fieldname: "project", label: "Project", options: "Project", reqd: 1,
					get_query: () => ({ filters: { company: d.get_value("company") } }),
				},
				{ fieldtype: "Column Break" },
				{ fieldtype: "Date", fieldname: "transaction_date", label: "Transaction Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Date", fieldname: "schedule_date", label: "Required By", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Link", fieldname: "warehouse", label: "Source Warehouse", options: "Warehouse",
					get_query: () => ({ filters: { company: d.get_value("company"), is_group: 0 } }),
					description: "Applied to every Raw Material row below.",
					onchange: () => this._apply_warehouse_to_items(d),
				},
				{
					fieldtype: "Link", fieldname: "routing", label: "Routing", options: "Routing", reqd: 1,
					description: "Determines the operation chain (and Work Order stages) for this run.",
					onchange: () => this._rebuild_fg_rows(d),
				},
				{ fieldtype: "Section Break", label: "Raw Materials" },
				{
					fieldtype: "Table", fieldname: "items", label: "Items", reqd: 1,
					in_place_edit: true,
					data: [],
					on_add_row: (idx) => {
						const row = (d.fields_dict.items.df.data || [])[idx - 1];
						if (!row) return;
						row.name = row.name || new_row_name();
						row.qty = row.qty || 1;
						row.warehouse = d.get_value("warehouse") || row.warehouse;
						d.fields_dict.items.grid.refresh();
					},
					fields: [
						{
							fieldtype: "Link", fieldname: "item_code", label: "Item", options: "Item", in_list_view: 1, reqd: 1, columns: 3,
							onchange: function () {
								const row = this.doc;
								if (!row) return;
								if (!row.warehouse && d.get_value("warehouse")) row.warehouse = d.get_value("warehouse");
								self._fetch_item_stock(d, row).then(() => self._on_rm_changed(d));
							},
						},
						{
							fieldtype: "Float", fieldname: "qty", label: "Qty (LBS)", in_list_view: 1, reqd: 1, columns: 1, default: 1,
							onchange: () => setTimeout(() => self._calculate_finished_qty(d), 0),
						},
						{
							fieldtype: "Link", fieldname: "warehouse", label: "Warehouse", options: "Warehouse", in_list_view: 1, columns: 2,
							onchange: function () { if (this.doc) self._fetch_item_stock(d, this.doc); },
						},
						{ fieldtype: "Float", fieldname: "actual_qty", label: "Actual Qty (Warehouse)", in_list_view: 1, read_only: 1, columns: 2 },
						{ fieldtype: "Float", fieldname: "total_qty", label: "Total Qty (All)", in_list_view: 1, read_only: 1, columns: 2 },
						{ fieldtype: "Data", fieldname: "stock_uom", label: "Stock UOM", read_only: 1 },
					],
				},
				{ fieldtype: "Section Break", label: "Finished Product Specification" },
				{
					fieldtype: "HTML", fieldname: "fg_hint",
					options: '<div class="text-muted small" style="margin-bottom:6px;">Rows are generated from Raw Materials × Routing operations (one row per raw material per operation). ' +
						'<a href="#" class="mc-rebuild-fg">↻ Rebuild rows from Routing</a> · <a href="#" class="mc-recalc-fg">Recalculate yields</a></div>',
				},
				{
					fieldtype: "Table", fieldname: "finished_goods", label: "Finished Goods",
					cannot_add_rows: true, in_place_edit: true,
					data: [],
					fields: [
						{
							fieldtype: "Link", fieldname: "item", label: "Item", options: "Item", in_list_view: 1, columns: 2,
							onchange: function () {
								const row = this.doc;
								if (!row || !row.item) return;
								frappe.db.get_value("Item", row.item, "custom_yield_percentage").then(r => {
									row.expected_yield_ = flt(r.message && r.message.custom_yield_percentage);
									self._calculate_finished_qty(d);
								});
							},
						},
						{ fieldtype: "Link", fieldname: "operation", label: "Operation", options: "Operation", in_list_view: 1, read_only: 1, columns: 2 },
						{
							fieldtype: "Percent", fieldname: "expected_yield_", label: "Expected Yield %", in_list_view: 1, columns: 1,
							onchange: () => setTimeout(() => self._calculate_finished_qty(d), 0),
						},
						{ fieldtype: "Float", fieldname: "finished_qty_grams", label: "Finished Qty (Grams)", in_list_view: 1, read_only: 1, columns: 1 },
						{ fieldtype: "Float", fieldname: "finished_qty_pounds", label: "Finished Qty (Pounds)", in_list_view: 1, read_only: 1, columns: 1 },
						{ fieldtype: "Link", fieldname: "source_warehouse", label: "Source Warehouse", options: "Warehouse", in_list_view: 1, columns: 1 },
						{ fieldtype: "Link", fieldname: "wip_warehouse", label: "WIP Warehouse", options: "Warehouse", in_list_view: 1, columns: 1 },
						{ fieldtype: "Link", fieldname: "target_warehouse", label: "Target Warehouse", options: "Warehouse", in_list_view: 1, columns: 1 },
					],
				},
				{ fieldtype: "Section Break" },
				{ fieldtype: "Check", fieldname: "submit", label: "Submit immediately", default: 1 },
			],
			primary_action_label: "Create request",
			primary_action: async (values) => {
				if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
				const items = (d.fields_dict.items.df.data || []).filter(r => r.item_code);
				if (values.routing) this._calculate_finished_qty(d);
				const fg_rows = (d.fields_dict.finished_goods.df.data || []).filter(r => r.operation);
				try {
					await this.api("create_material_request", {
						payload: JSON.stringify({
							company: values.company,
							project: values.project,
							routing: values.routing,
							warehouse: values.warehouse,
							transaction_date: values.transaction_date,
							schedule_date: values.schedule_date,
							items: items.map(r => ({ item_code: r.item_code, qty: r.qty, warehouse: r.warehouse })),
							finished_goods: fg_rows.map(r => ({
								item: r.item,
								operation: r.operation,
								expected_yield_: r.expected_yield_,
								finished_qty_grams: r.finished_qty_grams,
								finished_qty_pounds: r.finished_qty_pounds,
								source_warehouse: r.source_warehouse,
								wip_warehouse: r.wip_warehouse,
								target_warehouse: r.target_warehouse,
							})),
							submit: values.submit ? 1 : 0,
						}),
					});
					d.hide();
					const first_item = (items[0] && items[0].item_code) || "raw materials";
					frappe.show_alert({ message: `Run started for ${esc(first_item)}`, indicator: "green" });
					this.load_picker();
				} catch (e) {
					frappe.msgprint(e.message || e);
				}
			},
		});
		d.show();

		d.$wrapper.on("click", ".mc-rebuild-fg", (e) => { e.preventDefault(); this._rebuild_fg_rows(d); });
		d.$wrapper.on("click", ".mc-recalc-fg", (e) => { e.preventDefault(); this._calculate_finished_qty(d); });
	}

	_apply_warehouse_to_items(dialog) {
		const wh = dialog.get_value("warehouse");
		const rows = dialog.fields_dict.items.df.data || [];
		if (!wh) return;
		rows.forEach(r => { r.warehouse = wh; });
		dialog.fields_dict.items.grid.refresh();
		rows.filter(r => r.item_code).forEach(r => this._fetch_item_stock(dialog, r));
	}

	async _fetch_item_stock(dialog, row) {
		if (!row || !row.item_code) {
			if (row) { row.actual_qty = 0; row.total_qty = 0; }
			dialog.fields_dict.items.grid.refresh();
			return;
		}
		try {
			const r = await this.api("get_item_stock", { item_code: row.item_code, warehouse: row.warehouse || null });
			row.actual_qty = flt(r.actual_qty);
			row.total_qty = flt(r.total_qty);
			row.stock_uom = r.stock_uom || "";
		} catch (e) {
			row.actual_qty = 0;
			row.total_qty = 0;
		}
		dialog.fields_dict.items.grid.refresh();
	}

	_on_rm_changed(dialog) {
		const rm_count = (dialog.fields_dict.items.df.data || []).filter(r => r.item_code).length;
		if (!dialog.get_value("routing") || !rm_count) return;
		const n_ops = dialog._mc_n_ops || 0;
		const fg_count = (dialog.fields_dict.finished_goods.df.data || []).length;
		if (!n_ops || fg_count !== rm_count * n_ops) {
			this._rebuild_fg_rows(dialog);
		} else {
			this._calculate_finished_qty(dialog);
		}
	}

	async _rebuild_fg_rows(dialog) {
		const routing = dialog.get_value("routing");
		const rm_rows = (dialog.fields_dict.items.df.data || []).filter(r => r.item_code);
		const field = dialog.fields_dict.finished_goods;

		if (!routing) {
			field.df.data = [];
			field.grid.refresh();
			return;
		}
		if (!rm_rows.length) {
			frappe.show_alert({ message: "Add Raw Material rows — Finished Goods will be built from them.", indicator: "orange" });
			return;
		}

		let op_rows;
		try {
			op_rows = await this.api("get_routing_operations", { routing });
		} catch (e) {
			frappe.msgprint(e.message || e);
			return;
		}
		const op_names = (op_rows || []).map(o => o.operation);
		if (!op_names.length) {
			frappe.msgprint(`Routing ${routing} has no operations.`);
			return;
		}

		const items = await frappe.db.get_list("Item", {
			filters: { custom_operation: ["in", op_names] },
			fields: ["name", "custom_operation", "custom_yield_percentage"],
			limit: 0,
		});
		const items_by_op = {};
		(items || []).forEach(it => {
			(items_by_op[it.custom_operation] = items_by_op[it.custom_operation] || []).push(it);
		});

		const previous = field.df.data || [];
		const rows = [];
		rm_rows.forEach(() => {
			op_names.forEach(op => {
				const prev = previous[rows.length];
				const keep = prev && prev.operation === op && prev.item ? prev : null;
				const matches = items_by_op[op] || [];
				const auto = matches.length === 1 ? matches[0] : null;
				rows.push({
					name: frappe.utils.get_random(10),
					idx: rows.length + 1,
					__islocal: 1,
					operation: op,
					item: keep ? keep.item : (auto ? auto.name : ""),
					expected_yield_: keep ? flt(keep.expected_yield_) : (auto ? flt(auto.custom_yield_percentage) : 0),
					source_warehouse: keep ? keep.source_warehouse : "",
					wip_warehouse: keep ? keep.wip_warehouse : "",
					target_warehouse: keep ? keep.target_warehouse : "",
					finished_qty_grams: 0,
					finished_qty_pounds: 0,
				});
			});
		});

		dialog._mc_n_ops = op_names.length;
		field.df.data = rows;
		this._calculate_finished_qty(dialog);
	}

	_calculate_finished_qty(dialog) {
		const LBS_TO_GRAM = 453.592;
		const rm_rows = (dialog.fields_dict.items.df.data || []).filter(r => r.item_code);
		const fg_rows = dialog.fields_dict.finished_goods.df.data || [];
		const n_ops = dialog._mc_n_ops || Math.round(fg_rows.length / (rm_rows.length || 1)) || 1;

		let rm_idx = -1;
		let input_grams = 0;
		fg_rows.forEach((row, i) => {
			if (i % n_ops === 0) {
				rm_idx++;
				const rm = rm_rows[rm_idx];
				input_grams = rm ? flt(rm.qty) * LBS_TO_GRAM : 0;
			}
			const yield_pct = flt(row.expected_yield_);
			if (yield_pct > 0) {
				const output_grams = input_grams * (yield_pct / 100);
				row.finished_qty_grams = Math.round(output_grams * 10000) / 10000;
				row.finished_qty_pounds = Math.round((output_grams / LBS_TO_GRAM) * 10000) / 10000;
				input_grams = output_grams;
			} else {
				row.finished_qty_grams = 0;
				row.finished_qty_pounds = 0;
			}
		});

		dialog.fields_dict.finished_goods.grid.refresh();
	}

	_render_ops_body(run, active_wo) {
		const multi_stage = run.work_orders.length > 1;
		const stage_idx = active_wo ? run.work_orders.indexOf(active_wo) : -1;
		const stage_line = (multi_stage && !run.complete)
			? `<div class="mc-step-desc">Stage ${stage_idx + 1} of ${run.work_orders.length}${active_wo ? " — " + esc(active_wo.item_name) : ""}</div>`
			: "";

		const all_job_cards = run.work_orders.flatMap(wo => wo.job_cards);

		let body;
		if (!run.work_orders.length) {
			body = `<div class="mc-step-desc">Not Run Started - Click Release to Start Orders</div>`;
		} else if (!all_job_cards.length) {
			body = `<div class="mc-step-desc">No job cards yet.</div>`;
		} else {
			const ordered = this._order_job_cards(all_job_cards);
			const wo_by_name = Object.fromEntries(run.work_orders.map(wo => [wo.name, wo]));
			body = `<div class="mc-run-operations-card">${ordered.map(jc => this._render_op_group(jc, wo_by_name[jc.work_order] || {})).join("")}</div>`;
		}

		return stage_line + body;
	}

	_order_job_cards(job_cards) {
		const OP_ORDER = ["Hash Processing", "Rosin Pressing"];
		return [...job_cards].sort((a, b) => {
			const ai = OP_ORDER.indexOf(a.operation);
			const bi = OP_ORDER.indexOf(b.operation);
			return (ai === -1 ? OP_ORDER.length : ai) - (bi === -1 ? OP_ORDER.length : bi);
		});
	}

	_render_op_group(jc, wo) {
		const timer_html = jc.sub_operations.length
			? `<div class="mc-sub-ops">${jc.sub_operations.map(so => this._render_sub_op_row(so, jc)).join("")}</div>`
			: this._render_whole_jc_timer(jc);

		const wo_attr = `data-wo="${esc(jc.work_order || "")}" data-jc="${esc(jc.name)}"`;
		const transfer = wo.transferred
			? `<span class="mc-op-btn mc-step-done">Material Transferred to WIP</span>`
			: `<button class="mc-op-btn mc-btn-pending" data-action="transfer_run" ${wo_attr}>Send Material to WIP</button>`;
		const output = wo.manufacture_entry
			? `<button class="mc-op-btn" data-action="view_output" ${wo_attr}>${esc(this._output_done_label(jc.operation))}</button>`
			: `<button class="mc-op-btn mc-btn-pending" data-action="create_sku" ${wo_attr}>${esc(this._sku_button_label(jc.operation))}</button>`;
		const micron_grams = (jc.micron_rows || []).reduce((t, r) => t + flt(r.grams_collected), 0);
		const output_qty = wo.manufacture_entry ? flt(jc.total_completed_qty) : micron_grams;
		const qty = ["Hash Processing", "Rosin Pressing"].includes(jc.operation) && output_qty
			? `<span class="mc-op-qty" title="${wo.manufacture_entry ? "Completed Qty" : "Microns total"}">${esc(String(flt(output_qty, 3)))} g</span>`
			: "";
		const micron_count = (jc.micron_rows || []).length;
		const microns = `<button class="mc-op-btn${micron_count ? "" : " mc-btn-pending"}" data-action="enter_microns" data-jc="${esc(jc.name)}">Microns${micron_count ? ` (${micron_count})` : ""}</button>`;
		const tiering = jc.operation === "Rosin Pressing" && jc.work_order
			? `<div class="mc-run-op-complete">${wo.tiering_entry
				? `<span class="mc-op-btn mc-step-done">Product Tiered</span>`
				: `<button class="mc-op-btn mc-btn-pending" data-action="tiering_product" data-wo="${esc(jc.work_order)}">Tiering Product</button>`}</div>`
			: "";

		return `
		<div class="mc-run-op-group">
			<div class="mc-run-op-title-row">
				<div class="mc-run-op-title">
					${esc(jc.operation)}${jc.workstation ? ` <span class="mc-muted">· ${esc(jc.workstation)}</span>` : ""}
					${jc.last_employee_name ? `<span class="mc-op-employee" title="Employee"><i class="ti ti-user" aria-hidden="true"></i> ${esc(jc.last_employee_name)}</span>` : ""}
				</div>
				${transfer}
			</div>
			${timer_html}
			<div class="mc-run-op-secondary-actions">${microns} ${output} ${qty}</div>
			${tiering}
		</div>`;
	}

	_output_done_label(operation) {
		const LABELS = { "Hash Processing": "Bubble Hash Created", "Rosin Pressing": "Rosin Created" };
		return LABELS[operation] || "Output Created";
	}

	_open_tiering_dialog(wo_name, doc, mr_name) {
		const LIST = { conversion_type: 1, raw_material_1: 2, qty_rm_1: 1, finished_good_1: 2, qty_fg_1: 1, target_warehouse: 2 };
		const company = doc.company;
		const skip = (df) => /^micron_|_microns$/.test(df.fieldname) || /_item_group$/.test(df.fieldname);

		const fields = frappe.meta.get_docfields("Conversion Entry Item").filter(df => !skip(df)).map(df => {
			const f = { ...df, in_list_view: LIST[df.fieldname] ? 1 : 0, columns: LIST[df.fieldname] || df.columns };
			if (df.fieldname === "source_warehouse" || df.fieldname === "target_warehouse") {
				f.get_query = () => ({ filters: { company, is_group: 0 } });
			} else if (df.fieldname === "conversion_type") {
				f.onchange = function () {
					const row = this.doc;
					if (!row) return;
					const m = /^(\d+) to (\d+)$/.exec(row.conversion_type || "") || [0, 1, 1];
					for (let n = +m[1] + 1; n <= 7; n++) ["raw_material_", "qty_rm_"].forEach(p => { row[p + n] = null; });
					for (let n = +m[2] + 1; n <= 3; n++) ["finished_good_", "qty_fg_"].forEach(p => { row[p + n] = null; });
					d.fields_dict.items.grid.refresh();
				};
			}
			return f;
		});

		const d = new frappe.ui.Dialog({
			title: `Tiering Product — ${doc.project || wo_name}`,
			size: "extra-large",
			fields: [
				{
					fieldtype: "Table", fieldname: "items", label: __("Conversion Item"), reqd: 1,
					fields,
					data: (doc.items || []).map((r, i) => ({ ...r, name: frappe.utils.get_random(10), idx: i + 1 })),
				},
			],
			primary_action_label: "Create & Submit",
			primary_action: async () => {
				if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
				const values = d.get_values();
				if (!values) return;
				d.disable_primary_action();
				try {
					const r = await this.api("create_tiering_conversion", { work_order: wo_name, items: values.items || [] });
					d.hide();
					frappe.msgprint({
						title: "Tiering Product done",
						indicator: "green",
						message: `Conversion Entry <a href="/app/conversion-entry/${encodeURIComponent(r.conversion_entry)}">${esc(r.conversion_entry)}</a> submitted,
							with Stock ${r.stock_entries.length === 1 ? "Entry" : "Entries"} ${r.stock_entries.map(n => `<a href="/app/stock-entry/${encodeURIComponent(n)}">${esc(n)}</a>`).join(", ")}.`,
					});
					await this._refresh_one(mr_name);
				} catch (e) {
					d.enable_primary_action();
					frappe.msgprint(e.message || e);
				}
			},
		});
		d.show();
		return d;
	}

	_sku_button_label(operation) {
		const LABELS = { "Hash Processing": "Create Bubble Hash", "Rosin Pressing": "Create Rosin" };
		return LABELS[operation] || "Create SKU";
	}

	_render_sub_op_row(so, jc) {
		const running = so.status === "active";
		const done = so.status === "done";
		const is_complete = jc.status === "Completed";
		const any_running = false;
		const ended = !!so.ended;

		let status_text = "—";
		if (running) status_text = "running";
		else if (done) status_text = this._fmt_mins(so.total_mins) + (ended ? " · ended" : "");
		const who = (running || done) && (so.employee_name || so.workstation)
			? `<div class="mc-sub-op-who">${so.employee_name ? `<i class="ti ti-user" aria-hidden="true"></i> ${esc(so.employee_name)}` : ""}${so.workstation ? ` <span class="mc-muted">· ${esc(so.workstation)}</span>` : ""}</div>`
			: "";
		const assign_btn = so.assigned_employee_name
			? `<span class="mc-assigned-name">${esc(so.assigned_employee_name)}</span>`
			: `<button class="mc-op-btn mc-btn-pending" data-action="assign_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}">Assign To</button>`;

		let btn = "";
		if (is_complete) {
			btn = `<span class="mc-op-done-check">✓</span>`;
		} else if (ended && done) {
			btn = `<button class="mc-op-btn" data-action="view_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}">View</button>`;
		} else if (running) {
			btn = `
			<button class="mc-op-btn" data-action="stop_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}">Pause</button>
			<button class="mc-op-btn mc-btn-pending" data-action="end_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}">End</button>`;
		} else if (done) {
			btn = `
			${assign_btn}
			<button class="mc-op-btn" data-action="start_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}" ${any_running ? "disabled" : ""}>Resume</button>
			<button class="mc-op-btn mc-btn-pending" data-action="end_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}">End</button>`;
		} else {
			btn = `${assign_btn} <button class="mc-op-btn mc-btn-pending" data-action="start_sub_op" data-jc="${esc(jc.name)}" data-op="${esc(so.operation)}" ${any_running ? "disabled" : ""}>Start</button>`;
		}

		return `
		<div class="mc-sub-op-row">
			<div class="mc-sub-op-name">${esc(so.operation)}${who}${this._render_note_input(jc, so.operation, so.note)}</div>
			<div class="mc-sub-op-status">${status_text}</div>
			<div class="mc-sub-op-actions">${btn}</div>
		</div>`;
	}

	_render_note_input(jc, operation, note) {
		return `<input type="text" class="mc-sub-op-note" maxlength="140" placeholder="Note"
			data-jc="${esc(jc.name)}" data-op="${esc(operation || "")}" value="${esc(note || "")}" title="Note for ${esc(operation || "")}">`;
	}

	async _save_note($input) {
		const job_card = $input.attr("data-jc");
		const operation = $input.attr("data-op");
		const note = ($input.val() || "").trim();
		const jc = this.find_job_card(job_card);
		const so = jc && (jc.sub_operations || []).find(s => s.operation === operation);
		const saved = (so ? so.note : jc && jc.note) || "";
		if (note === saved) return;
		try {
			const r = await this.api("save_sub_op_note", { job_card, operation, note });
			if (so) so.note = r.note; else if (jc) jc.note = r.note;
			this._flash_note(job_card, operation, "is-saved");
		} catch (e) {
			this._flash_note(job_card, operation, "is-error");
			frappe.msgprint(e.message || e);
		}
	}

	_flash_note(job_card, operation, cls) {
		const $input = this.$app.find(".mc-sub-op-note")
			.filter((i, el) => el.getAttribute("data-jc") === job_card && el.getAttribute("data-op") === operation);
		$input.addClass(cls);
		setTimeout(() => $input.removeClass(cls), 1200);
	}

	_render_whole_jc_timer(jc) {
		const running = !!jc.active_timer;
		const is_complete = jc.status === "Completed";
		let total_secs = flt(jc.total_time_in_mins) * 60;
		if (running) {
			total_secs += (Date.now() - new Date(jc.active_timer.from_time).getTime()) / 1000;
		}
		let btn = "";
		if (!is_complete) {
			btn = running
				? `<button class="mc-timer-btn mc-timer-pause mc-timer-btn-sm" data-action="pause_timer" data-jc="${esc(jc.name)}">⏸ Pause</button>`
				: (jc.assigned_employee_name
					? `<span class="mc-assigned-name">${esc(jc.assigned_employee_name)}</span>`
					: `<button class="mc-op-btn mc-btn-pending" data-action="assign_sub_op" data-jc="${esc(jc.name)}">Assign To</button>`)
					+ `<button class="mc-timer-btn mc-timer-start mc-timer-btn-sm" data-action="start_timer" data-jc="${esc(jc.name)}">▶ Start</button>`;
		}
		return `
		<div class="mc-whole-timer">
			<div class="mc-timer-display mc-timer-display-sm" data-jc-timer="${esc(jc.name)}">${this._fmt_secs(Math.floor(total_secs))}</div>
			<div class="mc-timer-actions">${btn}</div>
			${this._render_note_input(jc, jc.operation, jc.note)}
		</div>`;
	}

	_make_filter_control(selector, doctype, key, placeholder) {
		const control = frappe.ui.form.make_control({
			parent: this.$app.find(selector)[0],
			df: { fieldtype: "Link", options: doctype, fieldname: key, placeholder },
			render_input: true,
		});
		control.refresh();
		if (this[key]) control.set_value(this[key]);
		control.$input.on("change awesomplete-selectcomplete", () => {
			setTimeout(() => {
				const value = control.get_value() || null;
				if (value === this[key]) return;
				this[key] = value;
				this._apply_filters();
			}, 0);
		});
		return control;
	}

	_set_card_collapsed($card, collapsed) {
		$card.toggleClass("is-collapsed", collapsed);
		$card.find('[data-action="toggle_card"]')
			.text(collapsed ? "▸" : "▾")
			.attr("title", collapsed ? "Expand" : "Collapse")
			.attr("aria-expanded", collapsed ? "false" : "true");
	}

	async _ask_start(title, jc, so, on_confirm) {
		if (this.default_employee === null) {
			try { this.default_employee = await this.api("get_default_employee"); } catch (e) { this.default_employee = ""; }
		}
		const assigned = so ? so.assigned_employee : jc && jc.assigned_employee;
		const employee = assigned || (so && so.employee) || (jc && jc.last_employee) || this.default_employee || "";
		const workstation = (so && (so.workstation || so.default_workstation)) || (jc && jc.default_workstation) || "";
		const d = new frappe.ui.Dialog({
			title,
			fields: [
				{ fieldtype: "Datetime", fieldname: "from_time", label: "From", default: frappe.datetime.now_datetime(), reqd: 1 },
				{ fieldtype: "Link", fieldname: "employee", label: "Employee", options: "Employee", default: employee, reqd: 1,
					get_query: () => ({ filters: { status: "Active" } }) },
				{ fieldtype: "Link", fieldname: "workstation", label: "Workstation", options: "Workstation", default: workstation },
			],
			primary_action_label: "Confirm",
			primary_action: (v) => {
				d.hide();
				on_confirm(v);
			},
		});
		d.show();
	}

	_ask_time(title, label, on_confirm) {
		const d = new frappe.ui.Dialog({
			title,
			fields: [{ fieldtype: "Datetime", fieldname: "when", label, default: frappe.datetime.now_datetime(), reqd: 1 }],
			primary_action_label: "Confirm",
			primary_action: (v) => {
				d.hide();
				on_confirm(v.when);
			},
		});
		d.show();
	}

	_to_datetime_local(str) {
		if (!str) return "";
		return str.replace(" ", "T").split(".")[0];
	}
	_from_datetime_local(str) {
		return (str || "").replace("T", " ");
	}

	_render_time_logs_table(jc, operation, editable) {
		const rows = (jc.time_logs || []).filter(tl => tl.operation === operation);
		if (!rows.length) return '<div class="mc-empty" style="padding:12px;">No time logs yet.</div>';
		const body_rows = rows.map(tl => {
			const can_edit = editable && tl.to_time;
			const from_cell = can_edit
				? `<input type="datetime-local" step="1" class="mc-tl-time-input" data-idx="${tl.idx}" data-field="from" value="${this._to_datetime_local(tl.from_time)}">`
				: (tl.from_time ? esc(tl.from_time) : "—");
			const to_cell = can_edit
				? `<input type="datetime-local" step="1" class="mc-tl-time-input" data-idx="${tl.idx}" data-field="to" value="${this._to_datetime_local(tl.to_time)}">`
				: (tl.to_time ? esc(tl.to_time) : "running");
			const ws_cell = can_edit
				? `<div class="mc-tl-ws" data-idx="${tl.idx}" data-value="${esc(tl.workstation || "")}"></div>`
				: (tl.workstation ? esc(tl.workstation) : "—");
			return `
			<tr>
				<td>${from_cell}</td>
				<td>${to_cell}</td>
				<td>${ws_cell}</td>
			</tr>`;
		}).join("");
		return `
		<table class="mc-transfer-table">
			<thead><tr><th>From</th><th>To</th><th>Workstation</th></tr></thead>
			<tbody>${body_rows}</tbody>
		</table>`;
	}

	_open_view_time_modal(jc, so, mr_name) {
		const self = this;
		const d = new frappe.ui.Dialog({
			title: `${so.operation} — Time`,
			size: "large",
			fields: [
				{ fieldtype: "HTML", options: this._render_time_logs_table(jc, so.operation, true) },
			],
			primary_action_label: "Save",
			primary_action: async () => {
				d.hide();
				try {
					const by_idx = {};
					d.$wrapper.find(".mc-tl-time-input").each(function () {
						const $input = $(this);
						(by_idx[$input.data("idx")] = by_idx[$input.data("idx")] || {})[$input.data("field")] = $input.val();
					});
					for (const idx of Object.keys(by_idx)) {
						const row = by_idx[idx];
						if (!row.from || !row.to) continue;
						const ws_control = ws_controls[idx];
						await self.api("update_time_log_row", {
							job_card: jc.name,
							idx,
							from_time: self._from_datetime_local(row.from),
							to_time: self._from_datetime_local(row.to),
							workstation: ws_control ? (ws_control.get_value() || "") : undefined,
						});
					}
					frappe.show_alert({ message: "Time updated", indicator: "green" });
					if (mr_name) await self._refresh_one(mr_name);
				} catch (e) { frappe.msgprint(e.message || e); }
			},
		});
		d.show();

		const ws_controls = {};
		d.$wrapper.find(".mc-tl-ws").each(function () {
			const $cell = $(this);
			const control = frappe.ui.form.make_control({
				parent: this,
				df: { fieldtype: "Link", fieldname: `workstation_${$cell.data("idx")}`, options: "Workstation", placeholder: "Workstation" },
				render_input: true,
			});
			control.refresh();
			control.set_value($cell.data("value") || "");
			ws_controls[$cell.data("idx")] = control;
		});
	}

	_open_micron_modal(jc, mr_name) {
		const read_only = jc.docstatus !== 0;
		const sizes = ["150u", "120u - 73u", "45u"];
		const rows = (jc.micron_rows || []).map(r => ({ ...r }));
		if (!read_only) {
			sizes.filter(s => !rows.some(r => r.micron_size === s))
				.forEach(s => rows.push({ micron_size: s, quality_grade: "Full Melt" }));
		}
		const grams_total = () => (d.fields_dict.microns.df.data || [])
			.reduce((t, r) => t + flt(r.grams_collected), 0);
		const update_total = () => setTimeout(() => d.set_value("total_quantity", grams_total()), 50);
		const d = new frappe.ui.Dialog({
			title: `Microns — ${jc.operation}`,
			size: "extra-large",
			fields: [
				{
					fieldtype: "Table", fieldname: "microns", label: "Micron Collection Detail",
					in_place_edit: true,
					cannot_add_rows: read_only, cannot_delete_rows: read_only, read_only: read_only ? 1 : 0,
					data: rows.map((r, i) => ({ ...r, name: frappe.utils.get_random(10), idx: i + 1 })),
					fields: [
						{ fieldtype: "Link", fieldname: "item", label: "Item", options: "Item", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Select", fieldname: "micron_size", label: "Micron Size", options: "\n150u\n120u - 73u\n45u", in_list_view: 1, reqd: 1, columns: 2, read_only },
						{ fieldtype: "Float", fieldname: "grams_collected", label: "Grams Collected", in_list_view: 1, reqd: 1, columns: 1, read_only },
						{ fieldtype: "Select", fieldname: "quality_grade", label: "Quality Grade", options: "\nFull Melt\n4-Star\n3-Star\n2-Star\nFood Grade", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Link", fieldname: "collected_by", label: "Collected By", options: "Employee", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Data", fieldname: "notes", label: "Notes", in_list_view: 1, columns: 1, read_only },
					],
				},
				{ fieldtype: "Float", fieldname: "total_quantity", label: "Total Quantity", read_only: 1 },
				read_only ? { fieldtype: "HTML", options: '<p class="text-muted small">This Job Card is submitted — micron data is read-only.</p>' } : null,
			].filter(Boolean),
			primary_action_label: read_only ? "Close" : "Save",
			primary_action: async () => {
				if (read_only) { d.hide(); return; }
				if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
				const rows = (d.fields_dict.microns.df.data || [])
					.filter(r => r.grams_collected || r.item)
					.map(r => ({
						item: r.item || null,
						micron_size: r.micron_size,
						grams_collected: flt(r.grams_collected),
						quality_grade: r.quality_grade || null,
						collected_by: r.collected_by || null,
						notes: r.notes || null,
					}));
				const bad = rows.findIndex(r => !r.micron_size || !r.grams_collected);
				if (bad !== -1) {
					frappe.msgprint(`Row ${bad + 1}: Micron Size and Grams Collected are required.`);
					return;
				}
				try {
					await this.api("save_micron_data", { job_card: jc.name, rows: JSON.stringify(rows) });
					frappe.show_alert({ message: "Micron data saved", indicator: "green" });
					d.hide();
					await this._refresh_one(mr_name);
				} catch (e) { frappe.msgprint(e.message || e); }
			},
		});
		d.show();
		d.set_value("total_quantity", grams_total());
		d.fields_dict.microns.grid.wrapper.on("change click", update_total);
	}

	_show_sku_modal(preview, wo_name, mr_name) {
		const self = this;

		if (preview.not_ready) {
			frappe.msgprint(preview.reason || "Not all Job Cards are completed yet.");
			return;
		}

		const rows_html = (preview.rows || []).map(r => `
			<tr>
				<td><b>${esc(r.item_name || r.item_code)}</b></td>
				<td style="text-align:right">${flt(r.qty)} ${esc(r.uom)}</td>
				<td>${esc(r.warehouse || "—")}</td>
			</tr>`).join("");

		const already_submitted = preview.existing && preview.docstatus === 1;
		const status_note = preview.existing
			? `<p style="margin-top:10px;color:var(--mc-text-muted);font-size:13px;">Stock Entry <b>${esc(preview.name)}</b> — ${already_submitted ? "already submitted." : "created as draft, not yet submitted."}</p>`
			: "";

		const table_html = `
		<table class="mc-transfer-table">
			<thead><tr><th>Item</th><th style="text-align:right">Qty</th><th>Warehouse</th></tr></thead>
			<tbody>${rows_html || '<tr><td colspan="3">No items to record yet.</td></tr>'}</tbody>
		</table>${status_note}`;

		const d = new frappe.ui.Dialog({
			title: "Manufacture Stock Entry — Preview",
			fields: already_submitted
				? [{ fieldtype: "HTML", options: table_html }]
				: [
					{ fieldtype: "HTML", options: table_html },
					{
						fieldtype: "Datetime",
						fieldname: "posting_datetime",
						label: "Completed Date & Time",
						reqd: 1,
						default: frappe.datetime.now_datetime(),
						description: "When the run actually finished. The stock entry posts at this time.",
					},
				],
			primary_action_label: already_submitted ? "Close" : "Submit",
			primary_action: async (v) => {
				if (already_submitted) { d.hide(); return; }
				if (!v || !v.posting_datetime) return;
				d.hide();
				try {
					frappe.show_alert({ message: "Creating & submitting Stock Entry…", indicator: "blue" });
					const result = await self.api("create_manufacture_se", {
						work_order: wo_name,
						posting_datetime: v.posting_datetime,
					});
					if (result.created || result.submitted) {
						frappe.show_alert({ message: `Stock Entry ${esc(result.name || "")} submitted`, indicator: "green" });
					} else {
						frappe.msgprint(result.reason || "Could not create the Stock Entry.");
					}
					await self._refresh_one(mr_name);
				} catch (e) { frappe.msgprint(e.message || e); }
			},
		});
		d.show();
	}

	async show_transfer_modal(wo_name, mr_name) {
		try {
			const preview = await this.api("get_transfer_preview", { work_order: wo_name });

			if (preview.already_transferred) {
				frappe.msgprint("Material transfer has already been completed for this Work Order.");
				return;
			}
			if (!preview.rows.length) {
				frappe.msgprint("No materials pending transfer.");
				return;
			}

			const table_html = `
			<table class="mc-transfer-table">
				<thead><tr><th>Item</th><th>From</th><th>To WIP</th><th style="text-align:right">Qty</th></tr></thead>
				<tbody>
				${preview.rows.map(r => `
					<tr>
						<td><b>${esc(r.item_name || r.item_code)}</b></td>
						<td>${esc(r.from_warehouse || "—")}</td>
						<td>${esc(r.to_warehouse || "WIP")}</td>
						<td style="text-align:right"><b>${flt(r.qty)} ${esc(r.uom)}</b></td>
					</tr>
				`).join("")}
				</tbody>
			</table>`;

			const d = new frappe.ui.Dialog({
				title: `Transfer Materials — ${preview.item_name}`,
				fields: [
					{ fieldtype: "HTML", options: table_html },
					{
						fieldtype: "Datetime",
						fieldname: "posting_datetime",
						label: "Transfer Date & Time",
						reqd: 1,
						default: frappe.datetime.now_datetime(),
						description: "When the material actually moved. The Stock Entry posts at this time, not when this is confirmed.",
					},
				],
				primary_action_label: "Confirm Transfer",
				primary_action: async (values) => {
					if (!values.posting_datetime) return;
					try {
						d.hide();
						frappe.show_alert({ message: "Transferring materials…", indicator: "blue" });
						await this.api("execute_transfer", {
							work_order: wo_name,
							posting_datetime: values.posting_datetime,
						});
						frappe.show_alert({ message: `Materials transferred for ${esc(preview.item_name)}`, indicator: "green" });
						this._refresh_one(mr_name);
					} catch (e) { frappe.msgprint(e.message || e); }
				},
			});
			d.show();
		} catch (e) {
			frappe.msgprint(e.message || e);
		}
	}

	_start_live_sync() {
		this._live_doctypes = ["Job Card", "Work Order", "Material Request", "Stock Entry", "Conversion Entry"];
		this._pending_refresh = new Set();
		this._live_subscribe();
		frappe.realtime.on("list_update", (data) => this._on_live_update(data));
		$(this.page.wrapper).on("show", () => this._live_subscribe());
		setInterval(() => this._live_subscribe(), 60000);
	}

	_live_subscribe() {
		this._live_doctypes.forEach(dt => frappe.realtime.doctype_subscribe(dt));
	}

	async _on_live_update(data) {
		if (!data || !this._live_doctypes.includes(data.doctype)) return;
		if (!this.$app.is(":visible")) return;

		let work_order = null;
		if (data.doctype === "Stock Entry" || data.doctype === "Conversion Entry") {
			const field = data.doctype === "Stock Entry" ? "work_order" : "custom_work_order";
			const r = await frappe.db.get_value(data.doctype, data.name, field).catch(() => null);
			work_order = r && r.message && r.message[field];
			if (!work_order) return;
		}

		const hits = Object.entries(this.runs).filter(([mr, run]) =>
			(data.doctype === "Material Request" && mr === data.name)
			|| (run.work_orders || []).some(wo =>
				(data.doctype === "Work Order" && wo.name === data.name)
				|| (work_order && wo.name === work_order)
				|| (data.doctype === "Job Card" && (wo.job_cards || []).some(jc => jc.name === data.name))));

		if (!hits.length) {
			if (data.doctype === "Material Request" && !(window.cur_dialog && cur_dialog.display)) {
				clearTimeout(this._picker_timer);
				this._picker_timer = setTimeout(() => this.load_picker(), 800);
			}
			return;
		}

		hits.forEach(([mr]) => this._pending_refresh.add(mr));
		clearTimeout(this._refresh_timer);
		this._refresh_timer = setTimeout(() => {
			const mrs = [...this._pending_refresh];
			this._pending_refresh.clear();
			mrs.forEach(mr => this._refresh_one(mr, { quiet: true }));
		}, 500);
	}

	find_job_card(name) {
		for (const run of Object.values(this.runs)) {
			for (const wo of run.work_orders) {
				const jc = wo.job_cards.find(j => j.name === name);
				if (jc) return jc;
			}
		}
		return null;
	}

	_start_ticks() {
		this._stop_ticks();
		const running = [];
		for (const run of Object.values(this.runs)) {
			for (const wo of run.work_orders) {
				for (const jc of wo.job_cards) {
					if (!jc.sub_operations.length && jc.active_timer) running.push(jc);
				}
			}
		}
		if (!running.length) return;

		this.timer_interval = setInterval(() => {
			running.forEach(jc => {
				const from = new Date(jc.active_timer.from_time);
				const total = flt(jc.total_time_in_mins) * 60 + (Date.now() - from.getTime()) / 1000;
				const $el = this.$app.find(`[data-jc-timer="${jc.name}"]`);
				if ($el.length) $el.text(this._fmt_secs(Math.floor(total)));
			});
		}, 1000);
	}

	_stop_ticks() {
		if (this.timer_interval) {
			clearInterval(this.timer_interval);
			this.timer_interval = null;
		}
	}

	_fmt_secs(s) {
		const h = Math.floor(s / 3600);
		const m = Math.floor((s % 3600) / 60);
		const sec = s % 60;
		return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
	}

	_fmt_mins(mins) {
		if (!mins) return "0 min";
		const h = Math.floor(mins / 60);
		const m = Math.round(mins % 60);
		if (h) return `${h}h ${m}m`;
		return `${m} min`;
	}
}

function flt(v, precision) {
	const n = parseFloat(v) || 0;
	return precision == null ? n : Math.round(n * 10 ** precision) / 10 ** precision;
}

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}
