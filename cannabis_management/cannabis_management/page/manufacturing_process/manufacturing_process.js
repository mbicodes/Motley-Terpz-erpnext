frappe.pages["manufacturing-process"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Manufacturing Process",
		single_column: true,
	});
	page.main.html('<div id="mfg-control-app"></div>');
	new ManufacturingRun(page);
};

// One production "run" = one Manufacture-type Material Request. A run's
// chain of Finished Goods (e.g. Hash Processing -> Rosin Pressing) is one
// Work Order per stage (see cannabis_management.doc_hooks.material_request
// ._create_boms_from_mr) — the active stage is scoped to whichever Work
// Order isn't fully produced yet, cycling to the next stage once it is.
class ManufacturingRun {
	constructor(page) {
		this.page = page;
		this.$app = page.main.find("#mfg-control-app");
		this.picker_data = null;
		this.runs = {}; // material_request name -> get_run_detail() result
		this.timer_interval = null;
		// Sub-operations the worker explicitly "Ended" (vs. just paused) —
		// client-side only for this session, keyed by "<job_card>::<operation>".
		// Ended ones show a View/edit-time button instead of Resume.
		this.item_filter = null; // selected Item (item_code), or null
		this.project_filter = null; // selected Project, or null
		this.operation_filter = null; // selected Operation, or null
		this.collapsed = new Set(); // material_request names whose card body is folded
		this.toggled_by_hand = new Set(); // cards opened/closed by hand -- keep that choice
		this.default_employee = null; // Employee linked to the session user
		this.date_filter = null; // "YYYY-MM-DD" or null
		this.load_picker();
	}

	api(method, args) {
		return frappe.xcall("cannabis_management.api.manufacturing_process." + method, args);
	}

	// ── RUN PICKER (landing) ─────────────────────────────────────────────────

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

	// Every run's card is always fully expanded — Release up top, its
	// operations below — right here on this one page. Clicking never
	// navigates anywhere; nothing here is a "next step".
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
				<input type="date" class="mc-wo-search" id="mc-date-filter" title="Filter by Date" value="${this.date_filter ? esc(this.date_filter) : ""}">
				<button class="mc-btn mc-btn-secondary" data-action="collapse_all">Collapse All</button>
				<button class="mc-btn mc-btn-secondary" data-action="expand_all">Expand All</button>
				<button class="mc-btn mc-btn-primary" data-action="new_run">+ New Run</button>
				<button class="mc-btn mc-btn-secondary" data-action="refresh">↻ Refresh</button>
			</div>
		</div>
		<div class="mc-section">
			<div class="mc-run-list">${this._render_run_card_shells(filtered)}</div>
		</div>`;

		this.$app.html(html);
		this._observe_card_heights();
		this._bind_picker_events();
		this._load_all_run_details(filtered);
	}

	// Item (raw material or finished good), Project, Operation (from the
	// finished-goods rows) and transaction date — all exact, all optional,
	// combined with AND.
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

	// Re-renders the list + heading count in place after a filter changes —
	// cards already fetched stay cached, only newly-shown ones are fetched.
	_apply_filters() {
		const filtered = this._get_filtered_mrs();
		this.$app.find("#mc-active-runs-heading").text(`Active Runs - ${filtered.length}`);
		this.$app.find(".mc-run-list").html(this._render_run_card_shells(filtered));
		this._observe_card_heights();
		this._load_all_run_details(filtered);
	}

	_render_run_card_shells(mrs) {
		if (!mrs.length) return '<div class="mc-empty">No active runs — start one to get going.</div>';
		return mrs.map(m => this._render_run_card_shell(m)).join("");
	}

	_render_run_card_shell(m) {
		const { status_class, status_label } = this._run_status_badge(m.docstatus, m.status);
		const collapsed = this.collapsed.has(m.name);
		return `
		<div class="mc-run-card${collapsed ? " is-collapsed" : ""}" data-mr="${esc(m.name)}">
			<div class="mc-ops-card-head">
				<button class="mc-card-toggle" data-action="toggle_card" title="${collapsed ? "Expand" : "Collapse"}" aria-expanded="${collapsed ? "false" : "true"}">${collapsed ? "▸" : "▾"}</button>
				<div class="mc-ops-card-info">
					<div class="mc-run-card-title">${esc(m.primary_label)}</div>
					<div class="mc-run-meta">
						<span>${esc(m.project_name || "No Project")}</span>
						<span>${esc(m.primary_qty)} <a class="mc-open-desk-link" onclick="frappe.set_route('Form','Material Request','${esc(m.name)}')">Open in Desk</a></span>
						<span class="mc-status mc-status-${status_class}" data-role="run-status">${status_label}</span>
					</div>
				</div>
				<div class="mc-ops-card-actions">${this._render_release_action(m.work_order_count > 0)}</div>
			</div>
			<div class="mc-run-card-body"><div class="mc-loading" style="padding:20px 0;">Loading operations…</div></div>
		</div>`;
	}

	// The run's Material Request status: Draft, then Pending until released,
	// In Progress while its Work Orders run, Completed once all are produced
	// (overrides/mr_run_status.py).
	_run_status_badge(docstatus, status) {
		const status_label = docstatus === 0 ? "Draft" : (status || "Submitted");
		const status_class = status_label.toLowerCase().replace(/\s+/g, "-");
		return { status_class, status_label };
	}

	// Masonry: the list is a grid of short rows and each card spans as many
	// as its height needs, so the cards under a short one move up instead of
	// leaving a gap beside a tall one. Re-measured whenever a card resizes
	// (its body loads, it is expanded or collapsed).
	_observe_card_heights() {
		if (this._card_observer) this._card_observer.disconnect();
		const list = this.$app.find(".mc-run-list")[0];
		if (!list || typeof ResizeObserver === "undefined") return;
		const row = parseFloat(getComputedStyle(list).gridAutoRows) || 8;
		const gap = parseFloat(getComputedStyle(list).rowGap) || 0;
		const GUTTER = 16; // space kept under each card
		this._card_observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const card = entry.target;
				const span = Math.ceil((card.getBoundingClientRect().height + GUTTER + gap) / (row + gap));
				card.style.gridRowEnd = `span ${span}`;
			}
		});
		list.querySelectorAll(".mc-run-card").forEach((card) => this._card_observer.observe(card));
	}

	// Release is a one-time action: once the run has Work Orders it reads
	// "Released" and can't be pressed again.
	_render_release_action(released) {
		return released
			? `<span class="mc-btn mc-btn-sm mc-step-done">Released</span>`
			: `<button class="mc-btn mc-btn-sm mc-btn-pending" data-action="release_run">Release</button>`;
	}

	// Fetched in parallel; each card fills in with its own operations as
	// soon as its call resolves, instead of blocking the whole list. Runs
	// already cached (e.g. re-shown after a filter change) render instantly
	// instead of being re-fetched.
	async _load_all_run_details(mrs) {
		mrs.forEach(async (m) => {
			if (this.runs[m.name]) {
				this._render_run_card_body(m.name);
				return;
			}
			try {
				const run = await this.api("get_run_detail", { material_request: m.name });
				this.runs[m.name] = run;
				this._render_run_card_body(m.name);
			} catch (e) {
				this.$app.find(`.mc-run-card[data-mr="${m.name}"] .mc-run-card-body`)
					.html(`<div class="mc-empty">Error: ${esc(e.message || e)}</div>`);
			}
		});
	}

	async _refresh_one(mr_name) {
		try {
			const run = await this.api("get_run_detail", { material_request: mr_name });
			this.runs[mr_name] = run;
			this._render_run_card_body(mr_name);
		} catch (e) {
			frappe.msgprint(e.message || e);
		}
	}

	_render_run_card_body(mr_name) {
		const run = this.runs[mr_name];
		if (!run) return;
		const active_wo = run.work_orders.find(w => w.name === run.active_work_order);
		const $card = this.$app.find(`.mc-run-card[data-mr="${mr_name}"]`);

		// Each job card renders its own "Send Material to WIP" button
		// already carrying the right data-wo (its own jc.work_order) —
		// no header-level button to sync here anymore.
		let body = this._render_ops_body(run, active_wo);
		$card.find(".mc-run-card-body").html(body);
		$card.find(".mc-ops-card-actions").html(this._render_release_action(run.work_orders.length > 0));
		const badge = this._run_status_badge(run.material_request.docstatus, run.material_request.status);
		$card.find('[data-role="run-status"]')
			.attr("class", `mc-status mc-status-${badge.status_class}`)
			.text(badge.status_label);

		// A finished run keeps its card, collapsed by default -- unless
		// someone has opened or closed it by hand this session. "Finished"
		// includes Tiering Product: a Completed run with a Rosin stage stays
		// open until its product has been tiered.
		const tiering_pending = run.work_orders.some(wo =>
			(wo.job_cards || []).some(jc => jc.operation === "Rosin Pressing") && !wo.tiering_entry);
		if (run.complete && !tiering_pending && !this.toggled_by_hand.has(mr_name)) {
			this.collapsed.add(mr_name);
			this._set_card_collapsed($card, true);
		}

		this._start_ticks();
	}

	_bind_picker_events() {
		const self = this;
		const $app = this.$app;

		// render_picker() re-runs this on every Refresh — drop the previous
		// delegated handlers first, or each click would fire once per render.
		$app.off("click");

		$app.find('[data-action="new_run"]').click(() => self.show_new_mr_modal());
		$app.find('[data-action="refresh"]').click(() => self.load_picker());

		// Item + Project filters — Link fields, same as Operation below.
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

		// Operation filter — Link field against the Operation doctype.
		this.operation_filter_control = this._make_filter_control("#mc-operation-filter-wrap", "Operation", "operation_filter", "Filter by Operation");

		$app.find("#mc-date-filter").on("change", function () {
			self.date_filter = $(this).val() || null;
			self._apply_filters();
		});

		// Delegated on $app (not the individual card) so buttons inside a
		// card's operations body keep working after that body re-renders —
		// no per-card rebinding needed.
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

		// Start (and Resume, same action/button) always asks for From time,
		// Employee and Workstation first — pre-filled with defaults (now, the
		// last employee on this card or the user's own, the operation's
		// workstation), all editable; Confirm actually starts it.
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

		// "Pause" — stops the clock but keeps the sub-op resumable.
		$app.on("click", '[data-action="stop_sub_op"]', async function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const operation = $btn.data("op");
			$btn.prop("disabled", true).text("Pausing…");
			try {
				await self.api("pause_timer", { job_card: $btn.data("jc") });
				frappe.show_alert({ message: `Paused — ${esc(operation)}`, indicator: "orange" });
				await self._refresh_one(mr_name);
			} catch (e) {
				frappe.msgprint(e.message || e);
				$btn.prop("disabled", false).text("Pause");
			}
		});

		// "End" — if the timer's currently running, asks for a To time first
		// (defaults to now) and closes it with that; marks the sub-op ended
		// on the Job Card either way (row then switches to View instead of
		// Resume, and stays that way after a reload).
		$app.on("click", '[data-action="end_sub_op"]', function () {
			const $btn = $(this);
			if ($btn.prop("disabled")) return;
			const mr_name = $btn.closest(".mc-run-card").data("mr");
			const jc_name = $btn.data("jc");
			const operation = $btn.data("op");
			const jc = self.find_job_card(jc_name);
			const is_running = !!(jc && jc.active_timer && jc.active_timer.operation === operation);
			// Last timer on this card = every other sub-operation already
			// ended — that End also asks for the Completed Qty, which goes on
			// the Job Card's time log row.
			const others = ((jc && jc.sub_operations) || []).filter(s => s.operation !== operation);
			const is_last = !!jc && others.every(s => s.ended);

			const finish = async (v) => {
				$btn.prop("disabled", true).text("Ending…");
				try {
					await self.api("end_sub_operation", {
						job_card: jc_name,
						operation,
						to_time: v.to_time || null,
						completed_qty: is_last ? v.completed_qty : null,
					});
					frappe.show_alert({ message: `Ended — ${esc(operation)}`, indicator: "blue" });
					await self._refresh_one(mr_name);
				} catch (e) {
					frappe.msgprint(e.message || e);
				} finally {
					$btn.prop("disabled", false).text("End");
				}
			};

			if (!is_running && !is_last) {
				finish({});
				return;
			}
			const fields = [];
			if (is_running) {
				fields.push({ fieldtype: "Datetime", fieldname: "to_time", label: "To", default: frappe.datetime.now_datetime(), reqd: 1 });
			}
			if (is_last) {
				fields.push({
					fieldtype: "Float", fieldname: "completed_qty", label: "Completed Qty", reqd: 1,
					default: flt(jc.for_quantity),
					description: `Last timer on ${esc(jc.operation)} — saved as Completed Qty on this time log.`,
				});
			}
			const d = new frappe.ui.Dialog({
				title: `End — ${operation}`,
				fields,
				primary_action_label: "Confirm",
				primary_action: (v) => {
					d.hide();
					finish(v);
				},
			});
			d.show();
		});

		// "View" — shows the logged time, and it can be corrected manually
		// (From/To per row) right here too.
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

		// Assign To — pick who should run this (sub-)operation. Saved on the
		// Job Card, so Start pre-fills this employee for whoever opens it.
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

		// Create Bubble Hash / Create Rosin -- also what "Complete — Enter
		// Output" used to do: a Job Card still open asks for the output,
		// is completed, and the Manufacture entry is made and submitted
		// right after. A card already completed goes to the entry preview.
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
			const d = new frappe.ui.Dialog({
				title: `${label} — ${jc.operation}`,
				fields: [
					{ fieldtype: "Float", fieldname: "completed_qty", label: "Output Qty (grams)", reqd: 1,
						default: micron_grams || flt(jc.for_quantity) },
					{ fieldtype: "HTML", options: '<p style="color:var(--mc-gray);font-size:13px;">This finishes the operation and records the output as a Manufacture stock entry.</p>' },
				],
				primary_action_label: label,
				primary_action: async (v) => {
					d.hide();
					try {
						frappe.show_alert({ message: `${esc(label)}…`, indicator: "blue" });
						const result = await self.api("complete_job_card", { job_card: jc.name, completed_qty: v.completed_qty });
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

		// Bubble Hash Created / Rosin Created -- read-only look at the entry.
		$app.on("click", '[data-action="view_output"]', async function () {
			const mr_name = $(this).closest(".mc-run-card").data("mr");
			const wo_name = $(this).data("wo");
			if (!wo_name) return;
			try {
				const preview = await self.api("get_manufacture_se_preview", { work_order: wo_name });
				self._show_sku_modal(preview, wo_name, mr_name);
			} catch (e) { frappe.msgprint(e.message || e); }
		});

		// Tiering Product — stays on this page: a dialog holding the Conversion
		// Entry's own Conversion Item table, pre-filled from this Rosin
		// Pressing Work Order; Create & Submit saves and submits the entry the
		// standard way, with its Stock Entries.
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

	// ── NEW RUN ──────────────────────────────────────────────────────────────

	// Mirrors the Material Request form (material_request.js): same fields,
	// same Finished Goods Detail columns, same Routing × Raw Materials row
	// build and yield chaining (calculate_finished_qty).
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

	// Top "Source Warehouse" → every Raw Material row, then re-read each
	// row's actual qty for its (new) warehouse.
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

	// Raw Material rows changed — rebuild Finished Goods if the Routing is
	// already picked (row count depends on how many raw materials there
	// are), otherwise wait for Routing.
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

	// Same as the Material Request form's populate_fg_rows(): one Finished
	// Goods row per (raw material × Routing operation). Finished Item +
	// Expected Yield % are auto-filled only when exactly one Item declares
	// that Operation (Item.custom_operation); already-picked items on a
	// matching row are kept.
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

	// Port of material_request.js calculate_finished_qty(): each Raw
	// Material's qty (LBS → grams) is chained through its Routing-operation
	// cycle, each row's Expected Yield % applied to the previous row's output.
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

	// ── Body content for a run's card ───────────────────────────────────────

	// Body-only content for a run's card (the header with Release already
	// lives in the always-rendered card shell).
	_render_ops_body(run, active_wo) {
		const multi_stage = run.work_orders.length > 1;
		const stage_idx = active_wo ? run.work_orders.indexOf(active_wo) : -1;
		const stage_line = (multi_stage && !run.complete)
			? `<div class="mc-step-desc">Stage ${stage_idx + 1} of ${run.work_orders.length}${active_wo ? " — " + esc(active_wo.item_name) : ""}</div>`
			: "";

		// A multi-stage run has one Work Order per operation (e.g. Hash
		// Processing and Rosin Pressing are two separate Work Orders, not
		// two job cards on one) — job cards from every stage are shown
		// together here, not just the currently-"active" stage's, so both
		// operations stay visible at once.
		const all_job_cards = run.work_orders.flatMap(wo => wo.job_cards);

		let body;
		if (!run.work_orders.length) {
			body = `<div class="mc-step-desc">Not Run Started - Click Release to Start Orders</div>`;
		} else if (!all_job_cards.length) {
			body = `<div class="mc-step-desc">No job cards yet.</div>`;
		} else {
			// Every job card stays visible — completed ones too — each with
			// its own transfer / SKU / micron actions. Hash Processing
			// always renders before Rosin Pressing.
			const ordered = this._order_job_cards(all_job_cards);
			const wo_by_name = Object.fromEntries(run.work_orders.map(wo => [wo.name, wo]));
			body = `<div class="mc-run-operations-card">${ordered.map(jc => this._render_op_group(jc, wo_by_name[jc.work_order] || {})).join("")}</div>`;
		}

		return stage_line + body;
	}

	// Fixed operation order for display — Hash Processing before Rosin
	// Pressing — anything else keeps its original (creation) order after.
	_order_job_cards(job_cards) {
		const OP_ORDER = ["Hash Processing", "Rosin Pressing"];
		return [...job_cards].sort((a, b) => {
			const ai = OP_ORDER.indexOf(a.operation);
			const bi = OP_ORDER.indexOf(b.operation);
			return (ai === -1 ? OP_ORDER.length : ai) - (bi === -1 ? OP_ORDER.length : bi);
		});
	}

	// ── Per-operation group: timers, micron entry, complete action ──────────

	// Every step button is filled (mc-btn-pending) until its step is done;
	// then it reads what was done, white with black text. One-time steps
	// (Send Material to WIP, Tiering) can't be pressed again; the output
	// ones (Bubble Hash / Rosin Created) open the entry they made.
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
			<div class="mc-run-op-secondary-actions">${output} ${microns}</div>
			${tiering}
		</div>`;
	}

	_output_done_label(operation) {
		const LABELS = { "Hash Processing": "Bubble Hash Created", "Rosin Pressing": "Rosin Created" };
		return LABELS[operation] || "Output Created";
	}

	// The Conversion Item table of a Conversion Entry, in a dialog: its fields
	// come from the Conversion Entry Item doctype itself, so the per-type
	// Raw Material 2-7 / Finished Good 2-3 fields show and hide exactly as on
	// the form (their depends_on), with the form's warehouse and tag pickers.
	// Key columns show in the table; every other field is in the row's edit
	// form. Left out: the Tolling micron fields (they depend on the parent
	// form) and the item-group fields the entry fills in itself.
	_open_tiering_dialog(wo_name, doc, mr_name) {
		const TAGS = "cannabis_management.cannabis_management.custom.metric_tag.";
		const LIST = { conversion_type: 1, raw_material_1: 2, qty_rm_1: 1, finished_good_1: 2, qty_fg_1: 1, fg_1_tag: 1, target_warehouse: 2 };
		const company = doc.company;
		const skip = (df) => /^micron_|_microns$/.test(df.fieldname) || /_item_group$/.test(df.fieldname);

		const fields = frappe.meta.get_docfields("Conversion Entry Item").filter(df => !skip(df)).map(df => {
			const f = { ...df, in_list_view: LIST[df.fieldname] ? 1 : 0, columns: LIST[df.fieldname] || df.columns };
			if (df.fieldname === "source_warehouse" || df.fieldname === "target_warehouse") {
				f.get_query = () => ({ filters: { company, is_group: 0 } });
			} else if (/^rm_\d_tag$/.test(df.fieldname)) {
				f.get_query = (row) => ({ query: TAGS + "conversion_source_tags", filters: { warehouse: (row && row.source_warehouse) || "" } });
			} else if (/^fg_\d_tag$/.test(df.fieldname)) {
				f.get_query = (row) => ({ query: TAGS + "conversion_target_tags", filters: { warehouse: (row && row.target_warehouse) || "" } });
			} else if (df.fieldname === "conversion_type") {
				// As on the form: fields the new type doesn't use are cleared.
				f.onchange = function () {
					const row = this.doc;
					if (!row) return;
					const m = /^(\d+) to (\d+)$/.exec(row.conversion_type || "") || [0, 1, 1];
					for (let n = +m[1] + 1; n <= 7; n++) ["raw_material_", "qty_rm_"].forEach(p => { row[p + n] = null; }), row[`rm_${n}_tag`] = null;
					for (let n = +m[2] + 1; n <= 3; n++) ["finished_good_", "qty_fg_"].forEach(p => { row[p + n] = null; }), row[`fg_${n}_tag`] = null;
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
				const values = d.get_values();   // runs the table's own required-field checks
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

	// Create SKU is named after what the operation produces.
	_sku_button_label(operation) {
		const LABELS = { "Hash Processing": "Create Bubble Hash", "Rosin Pressing": "Create Rosin" };
		return LABELS[operation] || "Create SKU";
	}

	// Row state machine: Pending -> Start; Running -> Pause + End;
	// Paused (has time, not ended) -> Resume + End; Ended -> View (popup
	// shows the time, read-only — the chance to correct it was the
	// End-confirmation step).
	_render_sub_op_row(so, jc) {
		const running = so.status === "active";
		const done = so.status === "done";
		const is_complete = jc.status === "Completed";
		const any_running = !!jc.active_timer;
		const ended = !!so.ended;

		let status_text = "—";
		if (running) status_text = "running";
		else if (done) status_text = this._fmt_mins(so.total_mins) + (ended ? " · ended" : "");
		const who = (running || done) && (so.employee_name || so.workstation)
			? `<div class="mc-sub-op-who">${so.employee_name ? `<i class="ti ti-user" aria-hidden="true"></i> ${esc(so.employee_name)}` : ""}${so.workstation ? ` <span class="mc-muted">· ${esc(so.workstation)}</span>` : ""}</div>`
			: "";
		// Once someone is assigned, their name replaces the button as plain
		// text -- the assignment is final and cannot be picked again here.
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
			<div class="mc-sub-op-name">${esc(so.operation)}${who}</div>
			<div class="mc-sub-op-status">${status_text}</div>
			<div class="mc-sub-op-actions">${btn}</div>
		</div>`;
	}

	// Fallback for a Job Card whose operation has no defined sub-steps —
	// one Start/Pause timer for the whole operation, same as before
	// sub-operation timers existed.
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
		</div>`;
	}

	// ── Time-log popups ──────────────────────────────────────────────────────

	_make_filter_control(selector, doctype, key, placeholder) {
		const control = frappe.ui.form.make_control({
			parent: this.$app.find(selector)[0],
			df: { fieldtype: "Link", options: doctype, fieldname: key, placeholder },
			render_input: true,
		});
		control.refresh();
		if (this[key]) control.set_value(this[key]);
		control.$input.on("change awesomplete-selectcomplete", () => {
			// Link validation resolves after the input event — read it next tick.
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

	// Start / Resume popup: From time, Employee, Workstation — each
	// pre-filled with its default and editable.
	async _ask_start(title, jc, so, on_confirm) {
		if (this.default_employee === null) {
			try { this.default_employee = await this.api("get_default_employee"); } catch (e) { this.default_employee = ""; }
		}
		// Whoever was picked with Assign To comes first.
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

	// Small Datetime prompt used by both Start (asks "From") and End (asks
	// "To") — defaults to now, Confirm hands the chosen value to on_confirm.
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

	// "YYYY-MM-DD HH:MM:SS(.ffffff)" (what the backend sends) <-> the value
	// format <input type="datetime-local" step="1"> needs/produces.
	_to_datetime_local(str) {
		if (!str) return "";
		return str.replace(" ", "T").split(".")[0];
	}
	_from_datetime_local(str) {
		return (str || "").replace("T", " ");
	}

	// The time_logs table for one operation on a job card. Read-only unless
	// editable=true (the "View" popup) — then every closed row's From/To
	// becomes directly editable; the still-running row (if any) never is.
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
			// Filled with a Workstation Link control once the dialog is shown.
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

	// "View" — shows the logged time, editable: change From/To and the
	// Workstation on any closed row and Save corrects it.
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

	// ── Micron popup ─────────────────────────────────────────────────────────

	// The Job Card's own Micron Collection Detail table (same columns as on
	// the Job Card form), edited in a modal. A submitted Job Card can't take
	// changes, so it opens read-only.
	_open_micron_modal(jc, mr_name) {
		const read_only = jc.docstatus !== 0;
		const d = new frappe.ui.Dialog({
			title: `Microns — ${jc.operation}`,
			size: "extra-large",
			fields: [
				{
					fieldtype: "Table", fieldname: "microns", label: "Micron Collection Detail",
					in_place_edit: true,
					cannot_add_rows: read_only, cannot_delete_rows: read_only, read_only: read_only ? 1 : 0,
					data: (jc.micron_rows || []).map((r, i) => ({ ...r, name: frappe.utils.get_random(10), idx: i + 1 })),
					fields: [
						{ fieldtype: "Link", fieldname: "item", label: "Item", options: "Item", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Select", fieldname: "micron_size", label: "Micron Size", options: "\n150u\n120u - 73u\n45u", in_list_view: 1, reqd: 1, columns: 2, read_only },
						{ fieldtype: "Float", fieldname: "grams_collected", label: "Grams Collected", in_list_view: 1, reqd: 1, columns: 1, read_only },
						{ fieldtype: "Select", fieldname: "quality_grade", label: "Quality Grade", options: "\nFull Melt\n4-Star\n3-Star\n2-Star\nFood Grade", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Link", fieldname: "collected_by", label: "Collected By", options: "Employee", in_list_view: 1, columns: 2, read_only },
						{ fieldtype: "Data", fieldname: "notes", label: "Notes", in_list_view: 1, columns: 1, read_only },
					],
				},
				read_only ? { fieldtype: "HTML", options: '<p class="text-muted small">This Job Card is submitted — micron data is read-only.</p>' } : null,
			].filter(Boolean),
			primary_action_label: read_only ? "Close" : "Save",
			primary_action: async () => {
				if (read_only) { d.hide(); return; }
				if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
				const rows = (d.fields_dict.microns.df.data || [])
					.filter(r => r.micron_size || r.grams_collected || r.item)
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
	}

	// ── Create SKU modal — preview the Manufacture Stock Entry, then submit ──

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
			fields: [{ fieldtype: "HTML", options: table_html }],
			primary_action_label: already_submitted ? "Close" : "Submit",
			primary_action: async () => {
				if (already_submitted) { d.hide(); return; }
				d.hide();
				try {
					frappe.show_alert({ message: "Creating & submitting Stock Entry…", indicator: "blue" });
					const result = await self.api("create_manufacture_se", { work_order: wo_name });
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

	// ── Transfer modal ────────────────────────────────────────────────────────

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
				fields: [{ fieldtype: "HTML", options: table_html }],
				primary_action_label: "Confirm Transfer",
				primary_action: async () => {
					try {
						d.hide();
						frappe.show_alert({ message: "Transferring materials…", indicator: "blue" });
						await this.api("execute_transfer", { work_order: wo_name });
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

	// ── Event binding helpers ───────────────────────────────────────────────

	find_job_card(name) {
		for (const run of Object.values(this.runs)) {
			for (const wo of run.work_orders) {
				const jc = wo.job_cards.find(j => j.name === name);
				if (jc) return jc;
			}
		}
		return null;
	}

	// ── Live ticking for whole-Job-Card fallback timers, across all cards ────

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

	// ── Helpers ──────────────────────────────────────────────────────────────

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

// Optional precision rounds, like frappe's own flt (which this shadows).
function flt(v, precision) {
	const n = parseFloat(v) || 0;
	return precision == null ? n : Math.round(n * 10 ** precision) / 10 ** precision;
}

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}
