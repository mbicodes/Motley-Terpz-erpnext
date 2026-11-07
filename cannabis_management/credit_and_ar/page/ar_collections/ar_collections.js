(function () {
	const API = "cannabis_management.credit_and_ar.page.ar_collections.ar_collections.";
	const ROUTE = "ar-collections";
	const DOCTYPE = "AR Collection";
	const STAGES = [
		["To Collect", "--arc-c1"],
		["Reached Out", "--arc-c2"],
		["Promise to Pay", "--arc-c3"],
		["Payment Plan", "--arc-c4"],
		["Disputed", "--arc-c5"],
		["Escalated", "--arc-c6"],
		["Collected", "--arc-c7"],
	];
	const STAGE_COLOR = Object.fromEntries(STAGES);
	const COLLECTED = "Collected";
	const AGE_LABELS = ["0–30", "31–60", "61–90", "90+"];
	const DISPUTE_REASONS = ["Pricing", "Quality", "Payment not applied", "Incorrect invoice", "Other"];
	const ESCALATION_REASONS = [
		"No response",
		"Promises broken",
		"Installments missed",
		"Business closed",
		"Owner-managed client",
		"Other",
	];
	const METHODS = ["ACH", "Wire", "Check", "Zelle", "Cash"];
	const FREQUENCIES = ["Weekly", "Bi-weekly", "Monthly"];
	const CALL_TYPES = ["Call", "Email", "Text", "Meeting"];
	const OUTCOMES = [
		"Reached, will pay",
		"Reached, disputed",
		"Left voicemail",
		"No answer",
		"Asked for statement",
		"Email sent",
		"Reply received",
	];
	const EPS = 0.005;

	const esc = (s) =>
		String(s == null ? "" : s).replace(
			/[&<>"']/g,
			(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
		);
	const money = (v) => {
		const n = Number(v) || 0;
		const cents = Math.round(Math.abs(n) * 100) % 100 !== 0;
		return (
			(n < 0 ? "-$" : "$") +
			Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: 2 })
		);
	};
	const kmoney = (v) => {
		const n = Number(v) || 0;
		if (Math.abs(n) >= 1e6) return "$" + (n / 1e6).toFixed(2) + "M";
		if (Math.abs(n) >= 1e3) return "$" + (n / 1e3).toFixed(1) + "k";
		return money(n);
	};
	const m = (d) => moment(d, "YYYY-MM-DD");
	const fmt = (d) => (d ? m(d).format("MMM D, YYYY") : "");
	const fmtS = (d) => (d ? m(d).format("MMM D") : "");
	const iso = (mm) => mm.format("YYYY-MM-DD");
	const initials = (name) =>
		String(name || "?")
			.split(/[\s@.]+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((p) => p[0])
			.join("")
			.toUpperCase();
	const safe_url = (u) => (/^https?:\/\//i.test(String(u || "").trim()) ? String(u).trim() : "");
	const html_to_text = (html) => {
		const withBreaks = String(html || "").replace(/<br\s*\/?>/gi, "\n").replace(/<\/p>/gi, "\n");
		const doc = new DOMParser().parseFromString(withBreaks, "text/html");
		return (doc.body.textContent || "").trim();
	};
	const unpaid = (r) => Math.max(0, (r.amount || 0) - (r.paid || 0));
	const status_tag = (s) =>
		({ Paid: "ok", Missed: "bad", "Partially Paid": "warn" })[s] || "";

	function age_bar(a) {
		const t = (a || []).reduce((s, x) => s + x, 0);
		if (!t) return `<div class="arc-agebar" aria-hidden="true"></div>`;
		return `<div class="arc-agebar" aria-hidden="true">${a
			.map((v, i) => (v > 0 ? `<i style="width:${(v / t) * 100}%;background:var(--arc-a${i})"></i>` : ""))
			.join("")}</div>`;
	}

	function split_schedule(amount, count, first, frequency) {
		const cents = Math.round((Number(amount) || 0) * 100);
		count = parseInt(count, 10) || 0;
		if (count < 1 || cents <= 0 || !first) return [];
		const base = Math.floor(cents / count);
		const rows = [];
		for (let i = 0; i < count; i++) {
			const c = i === count - 1 ? cents - base * (count - 1) : base;
			let due = m(first);
			if (frequency === "Weekly") due = due.add(7 * i, "days");
			else if (frequency === "Bi-weekly") due = due.add(14 * i, "days");
			else due = due.add(i, "months");
			rows.push({ due: iso(due), amount: c / 100 });
		}
		return rows;
	}

	class ARCollectionsBoard {
		constructor(page, wrapper) {
			this.page = page;
			this.wrapper = wrapper;
			this.data = null;
			this.cards = [];
			this.collected_all = 0;
			this.drag_name = null;
			this.panel_name = null;
			this.panel = null;
			this.tab = "overview";
			this.seq = 0;
			this.pending = {};

			this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
			this.page.set_secondary_action(__("New Collection"), () => this.new_collection());
			this.make_layout();
			this.bind_events();
			this.bind_realtime();
			this.load();
		}

		make_layout() {
			this.$root = $(`
				<div class="arc-root">
					<section class="arc-top" aria-label="${__("Summary")}">
						<div class="arc-stats"></div>
						<div class="arc-fc">
							<div class="k"><span>${__("Expected collections, next 8 weeks")}</span><strong class="arc-fc-total"></strong></div>
							<div class="arc-bars"></div>
							<div class="k" style="margin-top:6px"><span>${__("From payment plan installments and promises to pay")}</span></div>
						</div>
					</section>
					<div class="arc-bar">
						<select class="arc-f-assign" aria-label="${__("Assigned to")}"></select>
						<select class="arc-f-age" aria-label="${__("Aging")}">
							<option value="">${__("All aging")}</option>
							<option value="1">${__("Has 31–60 days")}</option>
							<option value="2">${__("Has 61–90 days")}</option>
							<option value="3">${__("Has 90+ days")}</option>
						</select>
						<select class="arc-f-ledger" aria-label="${__("Ledger")}">
							<option value="">${__("All ledgers")}</option>
							<option value="New AR">${__("New AR")}</option>
							<option value="Legacy AR">${__("Legacy AR")}</option>
						</select>
						<select class="arc-f-collected" aria-label="${__("Collected")}">
							<option value="0">${__("Collected: last 30 days")}</option>
							<option value="1">${__("Collected: all")}</option>
						</select>
						<input class="arc-f-q" type="search" placeholder="${__("Search customer")}" aria-label="${__("Search customer")}">
						<div class="arc-legend" aria-label="${__("Aging legend")}">
							${AGE_LABELS.map((l, i) => `<span><i style="background:var(--arc-a${i})"></i>${l}</span>`).join("")}
						</div>
					</div>
					<div class="arc-board"><div class="arc-loading">${__("Loading collections…")}</div></div>
				</div>`).appendTo(this.page.main);
			this.$board = this.$root.find(".arc-board");
			this.$scrim = $('<div class="arc-scrim"></div>').appendTo(document.body);
			this.$panel = $(`
				<aside class="arc-panel" aria-hidden="true" role="dialog" aria-label="${__("Collection details")}">
					<div class="arc-p-h">
						<button class="arc-p-x" type="button" aria-label="${__("Close")}">×</button>
						<h2></h2>
						<div class="arc-p-sub"></div>
						<div class="arc-actions">
							<button class="btn btn-default btn-xs" type="button" data-act="statement">${__("Print Statement")}</button>
							<button class="btn btn-default btn-xs" type="button" data-act="email_statement">${__("Email Statement")}</button>
							<button class="btn btn-default btn-xs" type="button" data-act="email">${__("Email Customer")}</button>
							<button class="btn btn-default btn-xs" type="button" data-act="call">${__("Log Call")}</button>
							<button class="btn btn-default btn-xs" type="button" data-act="payment">${__("Record Payment")}</button>
						</div>
						<div class="arc-tabs" role="tablist">
							<button role="tab" type="button" data-tab="overview">${__("Overview")}</button>
							<button role="tab" type="button" data-tab="plan">${__("Payment Plan")}</button>
							<button role="tab" type="button" data-tab="calls">${__("Call Log")}</button>
							<button role="tab" type="button" data-tab="notes">${__("Notes")}</button>
						</div>
					</div>
					<div class="arc-p-b"></div>
				</aside>`).appendTo(document.body);
		}

		// ---------------------------------------------------------------- data

		load(quiet) {
			const seq = ++this.seq;
			if (!quiet && !this.cards.length) {
				this.$board.html(`<div class="arc-loading">${__("Loading collections…")}</div>`);
			}
			return frappe
				.xcall(API + "get_board", { collected_all: this.collected_all })
				.then((r) => {
					if (seq !== this.seq) return;
					this.data = r;
					this.cards = r.cards || [];
					this.fill_assignees();
					this.render();
					if (this.panel_name) this.load_panel();
				})
				.catch(() => {
					if (seq === this.seq && !quiet) {
						this.$board.html(`<div class="arc-loading">${__("Could not load the board.")}</div>`);
					}
				});
		}

		fill_assignees() {
			const $sel = this.$root.find(".arc-f-assign");
			const cur = $sel.val() || "";
			const seen = {};
			this.cards.forEach((c) => {
				if (c.assigned_to) seen[c.assigned_to] = c.assigned_name || c.assigned_to;
			});
			const opts = Object.entries(seen).sort((a, b) => a[1].localeCompare(b[1]));
			$sel.html(
				`<option value="">${__("Everyone")}</option>` +
					opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("") +
					`<option value="__none">${__("Unassigned")}</option>`
			);
			$sel.val(cur && (seen[cur] || cur === "__none") ? cur : "");
		}

		find(name) {
			return this.cards.find((c) => c.name === name);
		}

		put(card) {
			if (!card) return;
			const i = this.cards.findIndex((c) => c.name === card.name);
			if (i >= 0) this.cards[i] = card;
			else this.cards.push(card);
			this.fill_assignees();
			this.render();
			if (this.panel_name === card.name) this.load_panel();
		}

		refresh_customer(customer) {
			if (this.pending[customer]) return;
			this.pending[customer] = setTimeout(() => {
				delete this.pending[customer];
				frappe.xcall(API + "get_cards", { customer }).then((cards) => {
					this.cards = this.cards.filter((c) => c.customer !== customer).concat(cards || []);
					this.fill_assignees();
					this.render();
					const p = this.panel_name && this.find(this.panel_name);
					if (p && p.customer === customer) this.load_panel();
				});
			}, 400);
		}

		can_write() {
			return !!(this.data && this.data.can_write);
		}

		filtered() {
			const who = this.$root.find(".arc-f-assign").val();
			const age = this.$root.find(".arc-f-age").val();
			const ledger = this.$root.find(".arc-f-ledger").val();
			const q = (this.$root.find(".arc-f-q").val() || "").trim().toLowerCase();
			return this.cards.filter(
				(c) =>
					(!who || (who === "__none" ? !c.assigned_to : c.assigned_to === who)) &&
					(!age || (c.aging || [])[+age] > EPS) &&
					(!ledger || c.ledger === ledger) &&
					(!q || c.customer_name.toLowerCase().includes(q) || c.customer.toLowerCase().includes(q))
			);
		}

		// ---------------------------------------------------------------- render

		render() {
			if (!this.data) return;
			this.render_top();
			this.render_board();
		}

		render_top() {
			const today = this.data.today;
			const open = this.cards.filter((c) => c.stage !== COLLECTED);
			const total = open.reduce((s, c) => s + (c.outstanding || 0), 0);
			const ag = [0, 0, 0, 0];
			open.forEach((c) => (c.aging || []).forEach((v, i) => (ag[i] += v)));
			let plan_bal = 0;
			let plans = 0;
			open.forEach((c) => {
				if (!c.plan) return;
				plans++;
				c.plan.rows.forEach((r) => (plan_bal += unpaid(r)));
			});
			const end30 = iso(m(today).add(30, "days"));
			let exp30 = 0;
			open.forEach((c) => {
				if (c.plan) c.plan.rows.forEach((r) => r.due <= end30 && (exp30 += unpaid(r)));
				if (this.open_promise(c) && c.promise_date >= today && c.promise_date <= end30) exp30 += c.promise_amount;
			});
			const month_total = this.cards.reduce((s, c) => s + (c.month_collected || 0), 0);
			const stats = [
				[__("Total outstanding"), kmoney(total), __("{0} open customers", [open.length]), age_bar(ag), money(total)],
				[
					__("90+ days"),
					kmoney(ag[3]),
					__("{0}% of outstanding", [total ? Math.round((ag[3] / total) * 100) : 0]),
					"",
					money(ag[3]),
				],
				[
					__("Payment plan balance"),
					kmoney(plan_bal),
					plans === 1 ? __("1 active plan") : __("{0} active plans", [plans]),
					"",
					money(plan_bal),
				],
				[__("Expected next 30 days"), kmoney(exp30), __("Installments and promises"), "", money(exp30)],
				[__("Collected this month"), kmoney(month_total), m(today).format("MMMM YYYY"), "", money(month_total)],
			];
			this.$root.find(".arc-stats").html(
				stats
					.map(
						([k, v, s, x, full]) =>
							`<div class="arc-stat"><div class="k">${esc(k)}</div><div class="v" title="${esc(full)}">${esc(
								v
							)}</div><div class="s">${esc(s)}</div>${x}</div>`
					)
					.join("")
			);

			const monday = m(today).startOf("isoWeek");
			const weeks = [];
			for (let i = 0; i < 8; i++) {
				const s = iso(monday.clone().add(7 * i, "days"));
				const e = iso(monday.clone().add(7 * i + 6, "days"));
				let v = 0;
				open.forEach((c) => {
					if (c.plan) c.plan.rows.forEach((r) => r.due >= s && r.due <= e && (v += unpaid(r)));
					if (this.open_promise(c) && c.promise_date >= s && c.promise_date <= e) v += c.promise_amount;
				});
				weeks.push([s, v]);
			}
			const mx = Math.max(1, ...weeks.map((w) => w[1]));
			this.$root.find(".arc-fc-total").text(money(weeks.reduce((a, w) => a + w[1], 0)));
			this.$root.find(".arc-bars").html(
				weeks
					.map(
						([s, v]) =>
							`<div class="b" title="${esc(__("Week of {0}: {1}", [fmtS(s), money(v)]))}"><span>${
								v ? esc(kmoney(v)) : ""
							}</span><i style="height:${(v / mx) * 60}px"></i><span>${esc(fmtS(s))}</span></div>`
					)
					.join("")
			);
		}

		open_promise(c) {
			return c.stage === "Promise to Pay" && c.promise_status === "Open" && c.promise_date && c.promise_amount > 0;
		}

		render_board() {
			const cards = this.filtered();
			const editable = this.can_write();
			const html = STAGES.map(([stage, color]) => {
				const is_coll = stage === COLLECTED;
				const list = cards
					.filter((c) => c.stage === stage)
					.sort((a, b) =>
						is_coll
							? b.collected_amount - a.collected_amount || a.customer_name.localeCompare(b.customer_name)
							: b.outstanding - a.outstanding || a.customer_name.localeCompare(b.customer_name)
					);
				const total = list.reduce((s, c) => s + (is_coll ? c.collected_amount : c.outstanding) || 0, 0);
				return `<section class="arc-col" data-stage="${esc(stage)}" aria-label="${esc(__(stage))}">
					<div class="arc-col-h">
						<div class="name"><span class="arc-dot" style="background:var(${color})"></span>${esc(__(stage))}</div>
						<div class="sum">${esc(list.length === 1 ? __("1 customer") : __("{0} customers", [list.length]))}, ${esc(
					money(total)
				)}</div>
					</div>
					<div class="arc-col-b">${
						list.length
							? list.map((c) => this.card_html(c, editable)).join("")
							: `<div class="arc-empty">${esc(__("Drop a customer here"))}</div>`
					}</div>
				</section>`;
			}).join("");
			const scroll = this.$board.scrollLeft();
			this.$board.html(html);
			this.$board.scrollLeft(scroll);
		}

		tags(c) {
			const today = this.data.today;
			const t = [];
			if (c.missed) t.push(["bad", c.missed === 1 ? __("1 missed") : __("{0} missed", [c.missed])]);
			if (c.stage === "Promise to Pay" && c.promise_date && c.promise_date < today && c.promise_status !== "Kept")
				t.push(["bad", __("Promise date passed")]);
			if (c.stage !== COLLECTED && c.next_action_date && c.next_action_date <= today)
				t.push(["warn", __("Follow-up due")]);
			if (c.consider_escalation) t.push(["warn", __("Consider escalation")]);
			if (c.written_off) t.push(["warn", __("Written off")]);
			t.push(["", __(c.ledger)]);
			return t;
		}

		card_html(c, editable) {
			const is_coll = c.stage === COLLECTED;
			let mid = "";
			if (is_coll) {
				mid = `<div class="arc-tags"><span class="arc-tag ok">${esc(
					c.written_off ? __("Closed {0}", [fmtS(c.collected_on)]) : __("Paid in full {0}", [fmtS(c.collected_on)])
				)}</span></div>`;
			} else {
				mid = age_bar(c.aging);
				if (c.plan) {
					const n = c.plan.rows.length;
					const paid = c.plan.rows.filter((r) => r.status === "Paid").length;
					const nx = c.plan.rows.find((r) => r.status !== "Paid");
					const freq = [c.plan.frequency ? __(c.plan.frequency).toLowerCase() : "", c.plan.method ? __(c.plan.method) : ""]
						.filter(Boolean)
						.join(" ");
					mid += `<div class="arc-prog">${esc(__("{0} of {1} paid", [paid, n]))}${freq ? ", " + esc(freq) : ""}${
						nx ? "<br>" + esc(__("Next {0} on {1}", [money(unpaid(nx)), fmtS(nx.due)])) : ""
					}<div class="track"><i style="width:${n ? (paid / n) * 100 : 0}%"></i></div></div>`;
				}
				if (c.stage === "Promise to Pay" && c.promise_amount) {
					mid += `<div class="arc-prog">${esc(
						__("Promised {0} by {1}", [money(c.promise_amount), fmtS(c.promise_date)])
					)}</div>`;
				}
			}
			const tags = this.tags(c);
			const foot = c.next_action
				? c.next_action + (c.next_action_date ? ", " + fmtS(c.next_action_date) : "")
				: c.last_contact
				? __("Last contact {0}", [fmtS(c.last_contact)])
				: __("No contact logged");
			const who = c.assigned_name || c.assigned_to;
			return `<div class="arc-card" role="button" tabindex="0" draggable="${editable ? "true" : "false"}" data-name="${esc(
				c.name
			)}">
				<div class="arc-r1"><span class="arc-cust">${esc(c.customer_name)}</span><span class="arc-amt">${esc(
				money(is_coll ? c.collected_amount : c.outstanding)
			)}</span></div>
				${mid}
				<div class="arc-tags">${tags
					.map(([k, l]) => `<span class="arc-tag ${k}">${esc(l)}</span>`)
					.join("")}</div>
				<div class="arc-meta"><span title="${esc(foot)}">${esc(foot)}</span>${
				who
					? `<span class="arc-av" title="${esc(__("Assigned to {0}", [who]))}">${esc(initials(who))}</span>`
					: `<span class="arc-av" title="${esc(__("Unassigned"))}">–</span>`
			}</div>
			</div>`;
		}

		// ---------------------------------------------------------------- events

		bind_events() {
			const me = this;
			this.$root.find(".arc-f-assign, .arc-f-age, .arc-f-ledger").on("change", () => this.render_board());
			this.$root.find(".arc-f-q").on("input", frappe.utils.debounce(() => this.render_board(), 150));
			this.$root.find(".arc-f-collected").on("change", function () {
				me.collected_all = +this.value;
				me.load();
			});
			this.$board.on("click", ".arc-card", function () {
				me.open_panel(this.dataset.name);
			});
			this.$board.on("keydown", ".arc-card", function (e) {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					me.open_panel(this.dataset.name);
				}
			});
			this.$board.on("dragstart", ".arc-card", function (e) {
				if (!me.can_write()) {
					e.preventDefault();
					return;
				}
				me.drag_name = this.dataset.name;
				this.classList.add("dragging");
				const dt = e.originalEvent.dataTransfer;
				dt.effectAllowed = "move";
				dt.setData("text/plain", me.drag_name);
			});
			this.$board.on("dragend", ".arc-card", function () {
				this.classList.remove("dragging");
				me.$board.find(".arc-col").removeClass("over");
				setTimeout(() => (me.drag_name = null), 0);
			});
			this.$board.on("dragover", ".arc-col", function (e) {
				if (!me.drag_name) return;
				e.preventDefault();
				this.classList.add("over");
				e.originalEvent.dataTransfer.dropEffect = "move";
			});
			this.$board.on("dragleave", ".arc-col", function (e) {
				if (!this.contains(e.originalEvent.relatedTarget)) this.classList.remove("over");
			});
			this.$board.on("drop", ".arc-col", function (e) {
				e.preventDefault();
				this.classList.remove("over");
				const name = me.drag_name || e.originalEvent.dataTransfer.getData("text/plain");
				me.drag_name = null;
				const c = me.find(name);
				if (c && c.stage !== this.dataset.stage) me.request_move(c, this.dataset.stage);
			});

			this.$panel.on("click", ".arc-p-x", () => this.close_panel());
			this.$scrim.on("click", () => this.close_panel());
			this.$panel.on("click", ".arc-tabs button", function () {
				me.tab = this.dataset.tab;
				me.render_panel();
			});
			this.$panel.on("click", ".arc-actions button", function () {
				const p = me.panel;
				if (!p) return;
				const act = this.dataset.act;
				if (act === "statement") me.print_statement(p);
				else if (act === "email_statement") me.email_dialog(p, true);
				else if (act === "email") me.email_dialog(p, false);
				else if (act === "call") me.call_dialog(p);
				else if (act === "payment") me.record_payment(p);
			});
			$(document).on("keydown.arc_panel", (e) => {
				if (e.key === "Escape" && this.panel_name && !$(".modal.show").length) this.close_panel();
			});
		}

		bind_realtime() {
			this.subscribe();
			frappe.realtime.on("ar_collections_refresh", (d) => {
				if (d && d.customer) this.refresh_customer(d.customer);
			});
		}

		subscribe() {
			frappe.realtime.doctype_subscribe(DOCTYPE);
		}

		on_show() {
			this.subscribe();
			if (this.data) this.load(true);
		}

		// ---------------------------------------------------------------- stage moves

		request_move(c, stage) {
			if (!this.can_write()) {
				frappe.show_alert({ message: __("You do not have permission to update collections."), indicator: "red" }, 6);
				return;
			}
			if (stage === c.stage) return;
			if (stage === COLLECTED && c.outstanding > EPS) {
				frappe.msgprint({
					title: __("Balance outstanding"),
					indicator: "red",
					message: __(
						"{0} still has an outstanding balance of {1}. Record the payment or write off the balance first.",
						[esc(c.customer_name), money(c.outstanding)]
					),
				});
				return;
			}
			if (stage === "Payment Plan" && !c.plan) {
				this.plan_dialog(c);
				return;
			}
			const fields = [];
			if (stage === "Promise to Pay") {
				fields.push(
					{ fieldtype: "Date", fieldname: "promise_date", label: __("Promise date"), reqd: 1, default: iso(m(this.data.today).add(7, "days")) },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Currency", fieldname: "promise_amount", label: __("Amount"), reqd: 1, default: c.outstanding },
					{ fieldtype: "Section Break" },
					{ fieldtype: "Small Text", fieldname: "note", label: __("Note") }
				);
			} else if (stage === "Disputed") {
				fields.push(
					{ fieldtype: "Select", fieldname: "dispute_reason", label: __("Dispute reason"), reqd: 1, options: [""].concat(DISPUTE_REASONS) },
					{ fieldtype: "Small Text", fieldname: "dispute_details", label: __("Details") }
				);
			} else if (stage === "Escalated") {
				fields.push(
					{ fieldtype: "Select", fieldname: "escalation_reason", label: __("Escalation reason"), reqd: 1, options: [""].concat(ESCALATION_REASONS) },
					{ fieldtype: "Link", fieldname: "escalated_to", label: __("Escalate to"), options: "User", only_select: 1 }
				);
			}
			if (stage !== "Promise to Pay") {
				fields.push(
					{ fieldtype: "Small Text", fieldname: "note", label: __("Note"), description: __("What happened and what is next") },
					{ fieldtype: "Data", fieldname: "next_action", label: __("Next action"), default: c.next_action || "" },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Date", fieldname: "next_action_date", label: __("Next action date"), default: c.next_action_date || "" }
				);
			}
			const sub =
				stage === "Promise to Pay"
					? __("Record what the customer committed to.")
					: __("From {0}. Outstanding {1}.", [__(c.stage), money(c.outstanding)]);
			const d = new frappe.ui.Dialog({
				title: __("Move {0} to {1}", [c.customer_name, __(stage)]),
				fields: [{ fieldtype: "HTML", fieldname: "sub", options: `<div class="arc-dlg arc-sub">${esc(sub)}</div>` }].concat(fields),
				primary_action_label: stage === "Promise to Pay" ? __("Save promise") : __("Save update"),
				secondary_action_label: __("Cancel"),
				secondary_action: () => d.hide(),
				primary_action: (v) => {
					if (stage === "Promise to Pay" && (!v.promise_date || !(v.promise_amount > 0))) {
						frappe.msgprint(__("Enter a promise date and an amount greater than zero."));
						return;
					}
					if (stage === "Disputed" && !v.dispute_reason) {
						frappe.msgprint(__("Select a dispute reason before moving the card to Disputed."));
						return;
					}
					if (stage === "Escalated" && !v.escalation_reason) {
						frappe.msgprint(__("Select an escalation reason before moving the card to Escalated."));
						return;
					}
					d.get_primary_btn().prop("disabled", true);
					frappe
						.xcall(API + "move_stage", { name: c.name, stage, values: v })
						.then((card) => {
							d.hide();
							this.put(card);
							frappe.show_alert({ message: __("{0} moved to {1}", [c.customer_name, __(stage)]), indicator: "green" });
						})
						.finally(() => d.get_primary_btn().prop("disabled", false));
				},
			});
			d.$wrapper.addClass("arc-dlg");
			d.show();
		}

		plan_dialog(c) {
			const outstanding = c.outstanding || 0;
			if (outstanding <= EPS) {
				frappe.msgprint(__("{0} has no outstanding balance, so a payment plan cannot be set up.", [esc(c.customer_name)]));
				return;
			}
			let preview = () => {};
			const d = new frappe.ui.Dialog({
				title: __("Set up payment plan for {0}", [c.customer_name]),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "sub",
						options: `<div class="arc-dlg arc-sub">${esc(
							__("Outstanding {0}. The schedule is generated from the values below.", [money(outstanding)])
						)}</div>`,
					},
					{ fieldtype: "Currency", fieldname: "plan_amount", label: __("Plan amount"), reqd: 1, default: outstanding, onchange: () => preview() },
					{ fieldtype: "Select", fieldname: "plan_frequency", label: __("Frequency"), reqd: 1, options: FREQUENCIES, default: "Monthly", onchange: () => preview() },
					{ fieldtype: "Int", fieldname: "plan_installments", label: __("Number of installments"), reqd: 1, default: 6, onchange: () => preview() },
					{ fieldtype: "Date", fieldname: "plan_first_due_date", label: __("First due date"), reqd: 1, default: iso(m(this.data.today).add(7, "days")), onchange: () => preview() },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Select", fieldname: "payment_method", label: __("Payment method"), options: [""].concat(METHODS) },
					{ fieldtype: "Small Text", fieldname: "payment_instructions", label: __("Payment instructions"), description: __("How and where the customer pays, and what to reference") },
					{ fieldtype: "Attach", fieldname: "plan_signed_document", label: __("Signed plan document") },
					{ fieldtype: "Section Break", label: __("Schedule preview") },
					{ fieldtype: "HTML", fieldname: "preview" },
				],
				primary_action_label: __("Create plan"),
				secondary_action_label: __("Cancel"),
				secondary_action: () => d.hide(),
				primary_action: (v) => {
					if (!(v.plan_amount > 0) || !(v.plan_installments > 0) || !v.plan_first_due_date) {
						frappe.msgprint(__("Enter a plan amount, the number of installments and the first due date."));
						return;
					}
					if (v.plan_amount > outstanding + EPS) {
						frappe.msgprint(__("The plan amount cannot be more than the outstanding balance of {0}.", [money(outstanding)]));
						return;
					}
					d.get_primary_btn().prop("disabled", true);
					frappe
						.xcall(API + "create_plan", { name: c.name, values: v })
						.then((card) => {
							d.hide();
							this.put(card);
							frappe.show_alert({ message: __("Payment plan created for {0}", [c.customer_name]), indicator: "green" });
						})
						.finally(() => d.get_primary_btn().prop("disabled", false));
				},
			});
			preview = () => {
				const v = d.get_values(true) || {};
				const rows = split_schedule(v.plan_amount, v.plan_installments, v.plan_first_due_date, v.plan_frequency);
				const $p = d.get_field("preview").$wrapper;
				if (!rows.length) {
					$p.html(`<div class="arc-dlg arc-box">${esc(__("Fill in the plan to see the schedule."))}</div>`);
					return;
				}
				const total = rows.reduce((s, r) => s + r.amount, 0);
				$p.html(`<div class="arc-dlg"><table><thead><tr><th>#</th><th>${__("Due date")}</th><th class="n">${__(
					"Amount"
				)}</th></tr></thead><tbody>${rows
					.map((r, i) => `<tr><td>${i + 1}</td><td>${esc(fmt(r.due))}</td><td class="n">${esc(money(r.amount))}</td></tr>`)
					.join("")}<tr><td colspan="2"><strong>${__("Total")}</strong></td><td class="n"><strong>${esc(
					money(total)
				)}</strong></td></tr></tbody></table></div>`);
			};
			d.$wrapper.addClass("arc-dlg");
			d.show();
			preview();
		}

		// ---------------------------------------------------------------- panel

		open_panel(name) {
			this.panel_name = name;
			this.tab = "overview";
			const c = this.find(name);
			this.panel = null;
			this.$panel.find("h2").text(c ? c.customer_name : "");
			this.$panel.find(".arc-p-sub").empty();
			this.$panel.find(".arc-p-b").html(`<div class="arc-loading">${__("Loading…")}</div>`);
			this.$panel.addClass("on").attr("aria-hidden", "false");
			this.$scrim.addClass("on");
			this.load_panel();
			setTimeout(() => this.$panel.find(".arc-p-x").trigger("focus"), 50);
		}

		close_panel() {
			this.panel_name = null;
			this.panel = null;
			this.$panel.removeClass("on").attr("aria-hidden", "true");
			this.$scrim.removeClass("on");
		}

		load_panel() {
			const name = this.panel_name;
			if (!name) return;
			frappe.xcall(API + "get_collection", { name }).then((p) => {
				if (this.panel_name !== name) return;
				this.panel = p;
				this.render_panel();
			});
		}

		render_panel() {
			const p = this.panel;
			if (!p) return;
			const today = this.data.today;
			this.$panel
				.find("h2")
				.html(`<a href="/app/ar-collection/${encodeURIComponent(p.name)}" title="${esc(__("Open the collection form"))}">${esc(p.customer_name)}</a>`);
			this.$panel.find(".arc-p-sub").html(
				`<span class="arc-dot" style="background:var(${STAGE_COLOR[p.stage]})"></span>${esc(__(p.stage))}, ${esc(
					p.stage === COLLECTED
						? p.written_off
							? __("closed with a write-off")
							: __("paid in full")
						: __("{0} outstanding", [money(p.outstanding)])
				)} · ${esc(__(p.ledger))}`
			);
			const write = p.can_write;
			this.$panel.find('[data-act="payment"]').prop("disabled", p.outstanding <= EPS || !this.data.can_payment);
			this.$panel.find('[data-act="email"], [data-act="email_statement"], [data-act="call"]').prop("disabled", !write);
			this.$panel.find(".arc-tabs button").each((_, b) => b.setAttribute("aria-selected", b.dataset.tab === this.tab));
			const $b = this.$panel.find(".arc-p-b");
			if (this.tab === "overview") $b.html(this.overview_html(p, write, today));
			else if (this.tab === "plan") $b.html(this.plan_html(p, write));
			else if (this.tab === "calls") $b.html(this.calls_html(p, write));
			else $b.html(this.notes_html(p, write));
			this.bind_panel($b, p);
		}

		overview_html(p, write, today) {
			const dis = write ? "" : "disabled";
			const users = (this.data.users || []).slice();
			if (p.assigned_to && !users.some((u) => u.value === p.assigned_to)) users.push({ value: p.assigned_to, label: p.assigned_to });
			const user_opts = (sel) =>
				`<option value=""></option>` +
				users.map((u) => `<option value="${esc(u.value)}" ${u.value === sel ? "selected" : ""}>${esc(u.label)}</option>`).join("");
			const sheet = safe_url(p.google_sheet_link);
			const cc = this.data.cc_email;
			let contact;
			if (!p.contact && !p.contact_email && !p.contact_phone) {
				contact = `<p class="arc-faint">${esc(__("No contact on file."))} ${
					write ? `<a href="#" data-do="add-contact">${esc(__("Add a contact"))}</a>` : ""
				}</p>`;
			} else {
				const mail = p.contact_email
					? `<a href="mailto:${encodeURIComponent(p.contact_email)}${cc ? "?cc=" + encodeURIComponent(cc) : ""}">${esc(p.contact_email)}</a>`
					: `<span class="arc-faint">${esc(__("No email on file"))}</span>`;
				const tel = p.contact_phone
					? `<a href="tel:${esc(String(p.contact_phone).replace(/[^\d+]/g, ""))}">${esc(p.contact_phone)}</a>`
					: `<span class="arc-faint">${esc(__("No phone on file"))}</span>`;
				contact = `<dl class="arc-kv">
					<dt>${__("Name")}</dt><dd>${
						p.contact ? `<a href="/app/contact/${encodeURIComponent(p.contact)}">${esc(p.contact_name || p.contact)}</a>` : `<span class="arc-faint">—</span>`
					}</dd>
					<dt>${__("Email")}</dt><dd>${mail}</dd>
					<dt>${__("Phone")}</dt><dd>${tel}</dd>
				</dl>${write ? `<p style="margin-top:6px"><a href="#" data-do="edit-contact">${esc(__("Change contact"))}</a></p>` : ""}`;
			}
			let extra = "";
			if (p.stage === "Disputed") {
				extra = `<h3>${__("Dispute")}</h3><dl class="arc-kv">
					<dt>${__("Reason")}</dt><dd><select data-f="dispute_reason" ${dis}>${[""].concat(DISPUTE_REASONS)
					.map((r) => `<option value="${esc(r)}" ${r === p.dispute_reason ? "selected" : ""}>${esc(__(r))}</option>`)
					.join("")}</select></dd>
					<dt>${__("Details")}</dt><dd><textarea data-f="dispute_details" rows="3" ${dis}>${esc(p.dispute_details)}</textarea></dd></dl>`;
			} else if (p.stage === "Escalated") {
				extra = `<h3>${__("Escalation")}</h3><dl class="arc-kv">
					<dt>${__("Reason")}</dt><dd><select data-f="escalation_reason" ${dis}>${[""].concat(ESCALATION_REASONS)
					.map((r) => `<option value="${esc(r)}" ${r === p.escalation_reason ? "selected" : ""}>${esc(__(r))}</option>`)
					.join("")}</select></dd>
					<dt>${__("Escalated to")}</dt><dd><select data-f="escalated_to" ${dis}>${user_opts(p.escalated_to)}</select></dd></dl>`;
			}
			if (p.write_off_journal_entry) {
				extra += `<h3>${__("Write-off")}</h3><p><a href="/app/journal-entry/${encodeURIComponent(p.write_off_journal_entry)}">${esc(
					p.write_off_journal_entry
				)}</a></p>`;
			}
			if (p.promises_broken) {
				extra += `<p class="arc-hint">${esc(
					p.promises_broken === 1 ? __("1 broken promise on this collection.") : __("{0} broken promises on this collection.", [p.promises_broken])
				)}</p>`;
			}
			const files = (p.files || [])
				.map((f) => `<li><a href="${esc(f.file_url)}" target="_blank" rel="noopener">${esc(f.file_name || f.file_url)}</a></li>`)
				.join("");
			return `<dl class="arc-kv">
					<dt>${__("Stage")}</dt><dd><select data-do="stage" ${dis}>${STAGES.map(
				([s]) => `<option value="${esc(s)}" ${s === p.stage ? "selected" : ""}>${esc(__(s))}</option>`
			).join("")}</select></dd>
					<dt>${__("Assigned to")}</dt><dd><select data-f="assigned_to" ${dis}>${user_opts(p.assigned_to)}</select></dd>
					<dt>${__("Next action")}</dt><dd><input data-f="next_action" value="${esc(p.next_action)}" ${dis}></dd>
					<dt>${__("Next action date")}</dt><dd><input type="date" data-f="next_action_date" value="${esc(p.next_action_date)}" ${dis}></dd>
				</dl>
				${extra}
				<h3>${__("Contact")}</h3>${contact}
				<h3>${__("Aging")}</h3>
				<div class="arc-tbl"><table><thead><tr>${AGE_LABELS.map((l) => `<th class="n">${l}</th>`).join("")}<th class="n">${__(
				"Total"
			)}</th></tr></thead><tbody><tr>${(p.aging || [])
				.map((v) => `<td class="n">${esc(money(v))}</td>`)
				.join("")}<td class="n"><strong>${esc(money(p.outstanding))}</strong></td></tr></tbody></table></div>
				${this.invoices_html(p, today)}
				<h3>${__("Google Sheet")}</h3>
				<dl class="arc-kv"><dt>${__("Link")}</dt><dd><input type="url" data-f="google_sheet_link" placeholder="https://docs.google.com/spreadsheets/..." value="${esc(
				p.google_sheet_link
			)}" ${dis}></dd></dl>
				${sheet ? `<p style="margin:6px 0 0"><a href="${esc(sheet)}" target="_blank" rel="noopener noreferrer">${esc(__("Open Google Sheet"))}</a></p>` : ""}
				<h3>${__("Attachments")}</h3>
				<ul class="arc-files">${files || `<li class="arc-faint">${esc(__("No attachments yet."))}</li>`}</ul>
				${write ? `<button class="btn btn-default btn-xs" type="button" data-do="attach">${esc(__("Attach file"))}</button>` : ""}`;
		}

		invoices_html(p, today) {
			if (!(p.invoices || []).length) return "";
			return `<h3>${__("Open invoices")}</h3><div class="arc-tbl"><table><thead><tr><th>${__("Invoice")}</th><th>${__(
				"Due date"
			)}</th><th class="n">${__("Days past due")}</th><th class="n">${__("Outstanding")}</th></tr></thead><tbody>${p.invoices
				.map((i) => {
					const days = i.due_date ? Math.max(0, m(today).diff(m(i.due_date), "days")) : 0;
					return `<tr><td><a href="/app/sales-invoice/${encodeURIComponent(i.name)}">${esc(i.name)}</a></td><td>${esc(
						fmt(i.due_date)
					)}</td><td class="n">${days}</td><td class="n">${esc(money(i.outstanding))}</td></tr>`;
				})
				.join("")}</tbody></table></div>`;
		}

		plan_html(p, write) {
			if (!p.plan) {
				return `<div class="arc-box">${esc(
					__("This customer has no payment plan. Move the card to Payment Plan, or set one up here.")
				)}</div>${
					write
						? `<p style="margin-top:12px"><button class="btn btn-primary btn-sm" type="button" data-do="plan" ${
								p.outstanding <= EPS ? "disabled" : ""
						  }>${esc(__("Set up payment plan"))}</button></p>`
						: ""
				}`;
			}
			const pl = p.plan;
			const total = pl.rows.reduce((s, r) => s + r.amount, 0);
			const paid = pl.rows.reduce((s, r) => s + r.paid, 0);
			const doc = safe_url(pl.signed_document) || (pl.signed_document && pl.signed_document.startsWith("/") ? pl.signed_document : "");
			return `<dl class="arc-kv">
					<dt>${__("Frequency")}</dt><dd>${esc(__(pl.frequency) || "—")}</dd>
					<dt>${__("Payment method")}</dt><dd>${esc(__(pl.method) || "—")}</dd>
					<dt>${__("Plan total")}</dt><dd>${esc(money(total))}</dd>
					<dt>${__("Paid to date")}</dt><dd>${esc(money(paid))} (${total ? Math.round((paid / total) * 100) : 0}%)</dd>
					<dt>${__("Remaining")}</dt><dd>${esc(money(total - paid))}</dd>
					<dt>${__("Plan created")}</dt><dd>${esc(fmt(pl.created_on))}</dd>
					${doc ? `<dt>${__("Signed plan")}</dt><dd><a href="${esc(doc)}" target="_blank" rel="noopener">${esc(__("Open document"))}</a></dd>` : ""}
				</dl>
				<h3>${__("How the customer pays")}</h3>
				<div class="arc-box">${esc(pl.instructions || __("No payment instructions entered."))}</div>
				<h3>${__("Installments")}</h3>
				<div class="arc-tbl"><table><thead><tr><th>#</th><th>${__("Due date")}</th><th class="n">${__("Amount")}</th><th class="n">${__(
				"Paid"
			)}</th><th>${__("Status")}</th></tr></thead><tbody>${pl.rows
				.map(
					(r, i) =>
						`<tr><td>${i + 1}</td><td>${esc(fmt(r.due))}</td><td class="n">${esc(money(r.amount))}</td><td class="n">${
							r.paid ? esc(money(r.paid)) : ""
						}</td><td><span class="arc-tag ${status_tag(r.status)}">${esc(__(r.status))}</span></td></tr>`
				)
				.join("")}</tbody></table></div>
				${
					pl.payments.length
						? `<h3>${__("Payments counted toward the plan")}</h3><div class="arc-tbl"><table><thead><tr><th>${__(
								"Payment Entry"
						  )}</th><th>${__("Date")}</th><th class="n">${__("Amount")}</th></tr></thead><tbody>${pl.payments
								.map(
									(x) =>
										`<tr><td><a href="/app/payment-entry/${encodeURIComponent(x.payment_entry)}">${esc(
											x.payment_entry
										)}</a></td><td>${esc(fmt(x.posting_date))}</td><td class="n">${esc(money(x.amount))}</td></tr>`
								)
								.join("")}</tbody></table></div>`
						: ""
				}
				<p class="arc-hint">${esc(
					__(
						"Each Payment Entry for this customer and ledger is applied to the oldest unpaid installment first. An installment past its due date and not fully paid is marked Missed and flags the card."
					)
				)}</p>
				${
					write
						? `<button class="btn btn-default btn-xs" type="button" data-do="edit-plan">${esc(__("Edit installments on the form"))}</button>`
						: ""
				}`;
		}

		calls_html(p, write) {
			const items = (p.calls || [])
				.map(
					(l) => `<li><div class="h"><span>${esc(
						__("{0}, {1} with {2}", [fmt(l.date), __(l.type), l.contact_person || __("customer")])
					)}</span><span>${esc(l.logged_by)}</span></div><div><strong>${esc(__(l.outcome))}</strong></div>${
						l.notes ? `<div class="tx">${esc(l.notes)}</div>` : ""
					}${l.follow_up_date ? `<div class="h" style="margin-top:4px">${esc(__("Follow up {0}", [fmt(l.follow_up_date)]))}</div>` : ""}</li>`
				)
				.join("");
			return `${
				write ? `<p><button class="btn btn-primary btn-sm" type="button" data-do="call">${esc(__("Log call"))}</button></p>` : ""
			}<ul class="arc-log">${items || `<li class="arc-faint">${esc(__("No calls logged yet."))}</li>`}</ul>`;
		}

		notes_html(p, write) {
			const items = (p.notes || [])
				.map(
					(n) =>
						`<li class="${n.type === "Info" ? "sys" : ""}"><div class="h"><span>${esc(n.by)}</span><span>${esc(
							moment(n.at).format("MMM D, YYYY h:mm A")
						)}</span></div><div class="tx">${esc(html_to_text(n.content))}</div></li>`
				)
				.join("");
			return `${
				write
					? `<div class="arc-note-in"><textarea data-do="note-text" placeholder="${esc(__("Add a note"))}"></textarea><button class="btn btn-primary btn-sm" type="button" data-do="note">${esc(
							__("Add note")
					  )}</button></div>`
					: ""
			}<ul class="arc-log">${items || `<li class="arc-faint">${esc(__("No notes yet."))}</li>`}</ul>`;
		}

		bind_panel($b, p) {
			const me = this;
			$b.find("[data-f]").on("change", function () {
				const f = this.dataset.f;
				const value = this.value;
				if (f === "google_sheet_link" && value && !safe_url(value)) {
					frappe.msgprint(__("Enter a link that starts with https://"));
					return;
				}
				frappe.xcall(API + "update_collection", { name: p.name, values: { [f]: value } }).then((card) => {
					me.put(card);
					frappe.show_alert({ message: __("Saved"), indicator: "green" }, 2);
				});
			});
			$b.find('[data-do="stage"]').on("change", function () {
				const stage = this.value;
				this.value = p.stage;
				const c = me.find(p.name) || Object.assign({}, p, { plan: p.plan ? { rows: p.plan.rows } : null });
				me.request_move(c, stage);
			});
			$b.find('[data-do="attach"]').on("click", () => {
				new frappe.ui.FileUploader({
					doctype: DOCTYPE,
					docname: p.name,
					on_success: () => {
						frappe.show_alert({ message: __("File attached"), indicator: "green" });
						me.load_panel();
					},
				});
			});
			$b.find('[data-do="plan"]').on("click", () => me.plan_dialog(me.find(p.name) || p));
			$b.find('[data-do="edit-plan"]').on("click", () => frappe.set_route("Form", DOCTYPE, p.name));
			$b.find('[data-do="call"]').on("click", () => me.call_dialog(p));
			$b.find('[data-do="note"]').on("click", function () {
				const text = ($b.find('[data-do="note-text"]').val() || "").trim();
				if (!text) return;
				$(this).prop("disabled", true);
				frappe
					.xcall(API + "add_note", { name: p.name, note: text })
					.then((data) => {
						me.panel = data;
						me.render_panel();
						frappe.show_alert({ message: __("Note added"), indicator: "green" });
					})
					.finally(() => $(this).prop("disabled", false));
			});
			$b.find('[data-do="add-contact"]').on("click", (e) => {
				e.preventDefault();
				frappe.dynamic_link = { doc: { name: p.customer, doctype: "Customer" }, fieldname: "name", doctype: "Customer" };
				frappe.new_doc("Contact");
			});
			$b.find('[data-do="edit-contact"]').on("click", (e) => {
				e.preventDefault();
				me.contact_dialog(p);
			});
		}

		contact_dialog(p) {
			const d = new frappe.ui.Dialog({
				title: __("Contact for {0}", [p.customer_name]),
				fields: [
					{
						fieldtype: "Link",
						fieldname: "contact",
						label: __("Contact"),
						options: "Contact",
						default: p.contact,
						get_query: () => ({
							query: "frappe.contacts.doctype.contact.contact.contact_query",
							filters: { link_doctype: "Customer", link_name: p.customer },
						}),
						description: __("Choosing a contact fills the email and phone from it."),
					},
					{ fieldtype: "Data", fieldname: "contact_email", label: __("Email"), options: "Email", default: p.contact_email },
					{ fieldtype: "Data", fieldname: "contact_phone", label: __("Phone"), default: p.contact_phone },
				],
				primary_action_label: __("Save"),
				primary_action: (v) => {
					const values = { contact: v.contact || "" };
					if ((v.contact || "") === (p.contact || "")) {
						values.contact_email = v.contact_email || "";
						values.contact_phone = v.contact_phone || "";
					}
					frappe.xcall(API + "update_collection", { name: p.name, values }).then((card) => {
						d.hide();
						this.put(card);
					});
				},
			});
			d.show();
		}

		// ---------------------------------------------------------------- actions

		print_statement(p) {
			const fmt_name = this.data.statement_print_format || "AR Collection Statement";
			const url =
				"/printview?doctype=" +
				encodeURIComponent(DOCTYPE) +
				"&name=" +
				encodeURIComponent(p.name) +
				"&format=" +
				encodeURIComponent(fmt_name) +
				"&no_letterhead=0";
			window.open(url, "_blank");
		}

		email_dialog(p, with_statement) {
			const cc = this.data.cc_email;
			const next = p.plan ? p.plan.rows.find((r) => r.status !== "Paid") : null;
			const greeting = p.contact_name ? __("Hello {0},", [p.contact_name]) : __("Hello,");
			const lines = [greeting, ""];
			let body = with_statement ? __("Please find attached your statement of account.") + " " : "";
			body += __("Our records show an outstanding balance of {0} on your account.", [money(p.outstanding)]);
			if (next) body += " " + __("Your next installment of {0} is due on {1}.", [money(unpaid(next)), fmt(next.due)]);
			lines.push(body, "");
			lines.push(
				__("Please let us know when we can expect payment, or reply to this email if anything on the account needs to be reviewed."),
				""
			);
			lines.push(__("Kind regards,"), frappe.session.user_fullname || "");
			const d = new frappe.ui.Dialog({
				title: __("Email {0}", [p.customer_name]),
				size: "large",
				fields: [
					{ fieldtype: "Data", fieldname: "to", label: __("To"), options: "Email", default: p.contact_email || "" },
					{
						fieldtype: "HTML",
						fieldname: "cc",
						options: cc
							? `<div class="arc-dlg form-group"><div class="control-label" style="margin-bottom:4px">${__("CC")}</div><span class="arc-chip">${esc(
									cc
							  )} <span>${esc(__("Always copied"))}</span></span></div>`
							: "",
					},
					{
						fieldtype: "Data",
						fieldname: "subject",
						label: __("Subject"),
						default: with_statement
							? __("Statement of account for {0}", [p.customer_name])
							: __("Outstanding balance for {0}", [p.customer_name]),
					},
					{ fieldtype: "Text", fieldname: "message", label: __("Message"), default: lines.join("\n") },
					{ fieldtype: "Check", fieldname: "attach_statement", label: __("Attach statement of account (PDF)"), default: with_statement ? 1 : 0 },
				],
				primary_action_label: __("Send email"),
				secondary_action_label: __("Cancel"),
				secondary_action: () => d.hide(),
				primary_action: (v) => {
					const to = (v.to || "").trim();
					if (!/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(to)) {
						frappe.msgprint(__("Enter a valid email address for the customer."));
						return;
					}
					d.get_primary_btn().prop("disabled", true);
					frappe
						.xcall(API + "send_email", {
							name: p.name,
							recipients: to,
							subject: v.subject,
							message: v.message,
							attach_statement: v.attach_statement ? 1 : 0,
						})
						.then((card) => {
							d.hide();
							this.put(card);
							frappe.show_alert({
								message: cc ? __("Email sent to {0}, CC {1}", [to, cc]) : __("Email sent to {0}", [to]),
								indicator: "green",
							});
						})
						.finally(() => d.get_primary_btn().prop("disabled", false));
				},
			});
			d.show();
		}

		call_dialog(p) {
			const d = new frappe.ui.Dialog({
				title: __("Log call for {0}", [p.customer_name]),
				fields: [
					{ fieldtype: "Date", fieldname: "call_date", label: __("Date"), reqd: 1, default: this.data.today },
					{ fieldtype: "Select", fieldname: "call_type", label: __("Type"), options: CALL_TYPES, default: "Call" },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Data", fieldname: "contact_person", label: __("Spoke with"), default: p.contact_name || "" },
					{ fieldtype: "Select", fieldname: "outcome", label: __("Outcome"), reqd: 1, options: [""].concat(OUTCOMES) },
					{ fieldtype: "Section Break" },
					{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes") },
					{ fieldtype: "Date", fieldname: "follow_up_date", label: __("Next follow-up date"), default: iso(m(this.data.today).add(3, "days")) },
				],
				primary_action_label: __("Save call"),
				secondary_action_label: __("Cancel"),
				secondary_action: () => d.hide(),
				primary_action: (v) => {
					d.get_primary_btn().prop("disabled", true);
					frappe
						.xcall(API + "log_call", { name: p.name, values: v })
						.then((card) => {
							d.hide();
							this.tab = this.panel_name === p.name ? "calls" : this.tab;
							this.put(card);
							frappe.show_alert({ message: __("Call logged"), indicator: "green" });
						})
						.finally(() => d.get_primary_btn().prop("disabled", false));
				},
			});
			d.show();
		}

		record_payment(p) {
			frappe.xcall(API + "make_payment_entry", { name: p.name }).then((doc) => {
				const list = frappe.model.sync(doc);
				this.close_panel();
				frappe.set_route("Form", list[0].doctype, list[0].name);
			});
		}

		new_collection() {
			if (!frappe.model.can_create(DOCTYPE)) {
				frappe.msgprint(__("You do not have permission to create a collection."));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("New collection"),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "sub",
						options: `<div class="arc-dlg arc-sub">${esc(
							__("Adds the customer to To Collect. The outstanding invoices are read from the customer's ledger.")
						)}</div>`,
					},
					{ fieldtype: "Link", fieldname: "customer", label: __("Customer"), options: "Customer", reqd: 1 },
					{ fieldtype: "Select", fieldname: "ledger", label: __("Ledger"), options: ["New AR", "Legacy AR"], default: "New AR", reqd: 1 },
					{
						fieldtype: "Link",
						fieldname: "assigned_to",
						label: __("Assigned to"),
						options: "User",
						default: (this.data && this.data.default_assignee) || "",
					},
				],
				primary_action_label: __("Add customer"),
				secondary_action_label: __("Cancel"),
				secondary_action: () => d.hide(),
				primary_action: (v) => {
					d.get_primary_btn().prop("disabled", true);
					frappe
						.xcall(API + "new_collection", v)
						.then((card) => {
							d.hide();
							this.put(card);
							frappe.show_alert({ message: __("{0} added to To Collect", [card.customer_name]), indicator: "green" });
						})
						.finally(() => d.get_primary_btn().prop("disabled", false));
				},
			});
			d.show();
		}
	}

	frappe.pages[ROUTE].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("AR Collections"),
			single_column: true,
		});
		wrapper.arc_board = new ARCollectionsBoard(page, wrapper);
	};

	frappe.pages[ROUTE].on_page_show = function (wrapper) {
		if (wrapper.arc_board) wrapper.arc_board.on_show();
	};

	frappe.pages[ROUTE].on_page_hide = function (wrapper) {
		if (wrapper.arc_board) wrapper.arc_board.close_panel();
	};
})();
