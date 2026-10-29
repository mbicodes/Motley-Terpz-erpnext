(function () {
	const IDLE_MINUTES = 45;
	const WARN_SECONDS = 60;
	const STORE_KEY = "idle_logout_last_activity";
	const LOGIN_COOKIE = "idle_login_at";
	const CHECK_EVERY_MS = 15 * 1000;
	const SAVE_EVERY_MS = 10 * 1000;

	const idle_ms = IDLE_MINUTES * 60 * 1000;
	let last_saved = 0;
	let warning = null;
	let logging_out = false;

	function login_at() {
		const m = document.cookie.match(new RegExp("(?:^|;\\s*)" + LOGIN_COOKIE + "=(\\d+)"));
		return m ? parseInt(m[1], 10) : 0;
	}

	function read() {
		try {
			const v = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
			if (v && v.login_at === login_at()) return v.t;
		} catch (e) {
		}
		return null;
	}

	function save(t) {
		last_saved = t;
		try {
			localStorage.setItem(STORE_KEY, JSON.stringify({ login_at: login_at(), t }));
		} catch (e) {
		}
	}

	let last_local = Date.now();

	function on_activity() {
		if (logging_out) return;
		const now = Date.now();
		last_local = now;
		if (warning) close_warning();
		if (now - last_saved > SAVE_EVERY_MS) save(now);
	}

	function last_activity() {
		return Math.max(last_local, read() || 0);
	}

	function logout() {
		if (logging_out) return;
		logging_out = true;
		close_warning();
		try {
			localStorage.removeItem(STORE_KEY);
		} catch (e) {}
		if (frappe.app && frappe.app.logout) {
			frappe.app.logout();
		} else {
			frappe.call({ method: "logout", callback: () => (window.location.href = "/login") });
		}
	}

	function close_warning() {
		if (!warning) return;
		const d = warning;
		warning = null;
		d.hide();
	}

	function show_warning(seconds_left) {
		if (warning) {
			warning.$wrapper.find(".idle-logout-left").text(seconds_left);
			return;
		}
		warning = new frappe.ui.Dialog({
			title: __("Still there?"),
			primary_action_label: __("Stay logged in"),
			primary_action() {
				on_activity();
			},
		});
		warning.$body.html(
			`<p>${__("You will be logged out in {0} seconds because there has been no activity for {1} minutes.", [
				'<b class="idle-logout-left">' + seconds_left + "</b>",
				IDLE_MINUTES,
			])}</p>`
		);
		warning.onhide = () => {
			if (warning) {
				warning = null;
				on_activity();
			}
		};
		warning.show();
	}

	function current_user() {
		return (frappe.session && frappe.session.user) || (frappe.boot && frappe.boot.user && frappe.boot.user.name);
	}

	function check() {
		if (logging_out || !current_user() || current_user() === "Guest") return;
		const left = idle_ms - (Date.now() - last_activity());
		if (left <= 0) logout();
		else if (left <= WARN_SECONDS * 1000) show_warning(Math.ceil(left / 1000));
		else if (warning) close_warning();
	}

	function start() {
		if (!window.frappe || !current_user() || current_user() === "Guest") return;

		const stored = read();
		if (stored && Date.now() - stored >= idle_ms) {
			logout();
			return;
		}
		save(Date.now());

		["mousemove", "mousedown", "keydown", "wheel", "touchstart", "scroll"].forEach((ev) =>
			document.addEventListener(ev, on_activity, { capture: true, passive: true })
		);
		setInterval(check, CHECK_EVERY_MS);
		document.addEventListener("visibilitychange", () => {
			if (document.visibilityState === "visible") check();
		});
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
	else start();
})();
