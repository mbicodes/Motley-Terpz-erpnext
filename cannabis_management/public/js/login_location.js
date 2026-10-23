// Login gate: on the login form, location must be allowed before the login request
// is sent. Runs in the capture phase so it sees the submit before Frappe's own
// login handler; once the browser grants access the form is submitted again and
// passes through. A refusal after login still ends the session server-side.
(function () {
	const EXEMPT = ["administrator"];
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
			// Nothing to ask without the API (old browser / plain http); the server
			// still records the login from its IP address.
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
					// Allowed but no fix (location services off, timeout): the user
					// did allow, so let them in; the server records Unavailable.
					if (err.code !== err.PERMISSION_DENIED) resubmit(form);
					else show_blocked();
				},
				{ timeout: 15000, maximumAge: 10 * 60 * 1000 }
			);
		},
		true
	);
})();

// Captures the user's real coordinates right after they log in and stores them as a
// User Login Location. The server sets the login_geo_pending cookie on login and
// clears it once a result is recorded — see time_clock/login_location.py.
(function () {
	const COOKIE = "login_geo_pending";
	const METHOD = "cannabis_management.time_clock.login_location.record";

	// Stop listening as soon as a fix is this good (metres)...
	const GOOD_ENOUGH_M = 20;
	// ...otherwise keep the best reading seen within this window. The first fix is
	// often a coarse network guess; GPS / Wi-Fi refine it over the next seconds.
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

	// The server has already ended the session; tell the user why, then send them
	// to the login page.
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
				// Start the clock at the first fix so time spent on the permission
				// prompt does not eat into the refinement window.
				if (!timer) timer = setTimeout(() => finish(), MAX_WAIT_MS);
				if (best.accuracy <= GOOD_ENOUGH_M) finish();
			},
			(err) => {
				// Timeouts between fixes are normal while refining; only give up on
				// a hard failure or if we never got a reading at all.
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
