(function () {
	const EXEMPT = ["administrator", "nikki@motleyterpz.com"];
	let allowed = false;
	let asking = false;

	function show_blocked() {
		const message = __(
			"Location access is required to log in. Allow location for this site (click the icon left of the address bar → Site settings → Location → Allow), then press Continue again."
		);
		if (window.frappe && frappe.msgprint) {
			frappe.msgprint({ title: __("Location Required"), message, indicator: "red" });
		} else {
			window.alert(message);
		}
	}

	function resubmit(form) {
		allowed = true;
		if (form.requestSubmit) form.requestSubmit();
		else form.querySelector("[type=submit]").click();
	}

	document.addEventListener(
		"submit",
		(event) => {
			const form = event.target;
			if (!form.classList || !form.classList.contains("form-login") || allowed) return;

			const user = ((form.querySelector("#login_email") || {}).value || "").trim().toLowerCase();
			if (EXEMPT.includes(user) || !navigator.geolocation) return;

			event.preventDefault();
			event.stopImmediatePropagation();
			if (asking) return;
			asking = true;

			navigator.geolocation.getCurrentPosition(
				() => {
					asking = false;
					resubmit(form);
				},
				(err) => {
					asking = false;
					if (err.code !== err.PERMISSION_DENIED) resubmit(form);
					else show_blocked();
				},
				{ timeout: 15000, maximumAge: 10 * 60 * 1000 }
			);
		},
		true
	);
})();

(function () {
	const COOKIE = "login_geo_pending";
	const METHOD = "cannabis_management.time_clock.login_location.record";

	const GOOD_ENOUGH_M = 20;
	const MAX_WAIT_MS = 30000;

	if (!document.cookie.split(/;\s*/).includes(`${COOKIE}=1`)) return;

	function send(args) {
		frappe.call({
			method: METHOD,
			type: "POST",
			args,
			freeze: false,
			callback(r) {
				const res = r.message || {};
				if (res.logged_out) {
					on_logged_out();
					return;
				}
				if (res.status === "Approximate" && frappe.show_alert) {
					frappe.show_alert(
						{
							message: __(
								"Your location could only be found to within {0} m. Turn on your device's location services (and Wi-Fi) for an exact position.",
								[Math.round(res.accuracy)]
							),
							indicator: "orange",
						},
						15
					);
				}
			},
		});
	}

	function on_logged_out() {
		const message = __(
			"You have been logged out because location access was blocked. Allow location for this site (click the icon left of the address bar → Site settings → Location → Allow), then log in again."
		);
		const go = () => (window.location.href = "/login");
		if (frappe.msgprint) {
			const d = frappe.msgprint({ title: __("Location Required"), message, indicator: "red" });
			if (d) {
				d.custom_onhide = go;
				return;
			}
		}
		window.alert(message);
		go();
	}

	function capture() {
		if (!navigator.geolocation) {
			send({ status: "Not Supported" });
			return;
		}

		let best = null;
		let done = false;
		let watchId = null;
		let timer = null;

		function finish(err) {
			if (done) return;
			done = true;
			clearTimeout(timer);
			if (watchId !== null) navigator.geolocation.clearWatch(watchId);

			if (best) {
				send({
					status: "Captured",
					latitude: best.latitude,
					longitude: best.longitude,
					accuracy: best.accuracy,
				});
			} else if (err) {
				send({
					status: err.code === err.PERMISSION_DENIED ? "Denied" : "Unavailable",
					error_message: err.message,
				});
			} else {
				send({ status: "Unavailable", error_message: "No position within time limit" });
			}
		}

		watchId = navigator.geolocation.watchPosition(
			(pos) => {
				if (!best || pos.coords.accuracy < best.accuracy) best = pos.coords;
				if (!timer) timer = setTimeout(() => finish(), MAX_WAIT_MS);
				if (best.accuracy <= GOOD_ENOUGH_M) finish();
			},
			(err) => {
				if (err.code === err.TIMEOUT && best) return;
				finish(err);
			},
			{ enableHighAccuracy: true, timeout: MAX_WAIT_MS, maximumAge: 0 }
		);
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", capture);
	} else {
		capture();
	}
})();
