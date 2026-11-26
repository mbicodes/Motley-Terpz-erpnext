(function () {
	"use strict";

	var WELCOME_KEY = "mlt-welcome";
	var WELCOME_WINDOW_MS = 120000;
	var WELCOME_MS = 3200;
	var GOODBYE_MIN_MS = 2600;
	var GESTURE_WINDOW_MS = 5000;
	var lastGesture = 0;

	function firstName() {
		var boot = window.frappe && frappe.boot;
		var user = boot && boot.user;
		var name = (user && (user.first_name || user.full_name)) ||
			(window.frappe && frappe.session && frappe.session.user_fullname) || "";
		return String(name).trim().split(/\s+/)[0] || "there";
	}

	function partOfDay(d) {
		var h = d.getHours();
		if (h < 12) return "morning";
		if (h < 17) return "afternoon";
		return "evening";
	}

	function clock(d) {
		return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
	}

	function farewell(d) {
		var day = d.getDay();
		var h = d.getHours();
		if ((day === 5 && h >= 12) || day === 6) return "Have a great weekend!";
		if (h >= 17) return "Have a good night!";
		return "See you next time!";
	}

	function takeWelcomeFlag() {
		try {
			var raw = sessionStorage.getItem(WELCOME_KEY);
			if (!raw) return false;
			sessionStorage.removeItem(WELCOME_KEY);
			return Date.now() - Number(raw) < WELCOME_WINDOW_MS;
		} catch (e) {
			return false;
		}
	}

	function showWelcome() {
		if (!window.MLTScene || !/^\/app(\/|$)/.test(location.pathname)) return;
		if (!takeWelcomeFlag()) return;
		var now = new Date();
		MLTScene.celebrate({
			tone: "in",
			kicker: "Signed in at " + clock(now),
			title: "Welcome back, " + firstName() + "!",
			message: "Good " + partOfDay(now) + "! Everything's ready for you.",
			duration: WELCOME_MS,
		});
	}

	function noteGesture() { lastGesture = Date.now(); }
	document.addEventListener("pointerdown", noteGesture, true);
	document.addEventListener("keydown", noteGesture, true);

	function patchLogout(target) {
		if (!target || target.__mltGoodbye || typeof target.logout !== "function") return false;
		var originalLogout = target.logout;

		target.logout = function () {
			var app = this;
			if (!window.MLTScene || Date.now() - lastGesture > GESTURE_WINDOW_MS) {
				return originalLogout.apply(app, arguments);
			}

			var started = Date.now();
			var now = new Date();
			var originalRedirect = app.redirect_to_login;
			var screen = MLTScene.celebrate({
				tone: "out",
				kicker: "Signed out at " + clock(now),
				title: "Goodbye, " + firstName() + "!",
				message: "You're signed out safely.",
				foot: farewell(now),
				dismissible: false,
			});

			var safety = setTimeout(function () {
				app.redirect_to_login = originalRedirect;
				screen.dismiss();
			}, 12000);

			app.redirect_to_login = function () {
				var args = arguments;
				clearTimeout(safety);
				setTimeout(function () {
					originalRedirect.apply(app, args);
				}, Math.max(0, GOODBYE_MIN_MS - (Date.now() - started)));
			};

			return originalLogout.apply(app, arguments);
		};
		target.__mltGoodbye = true;
		return true;
	}

	if (!(window.frappe && frappe.Application && patchLogout(frappe.Application.prototype))) {
		document.addEventListener("DOMContentLoaded", function () {
			if (window.frappe && frappe.app) patchLogout(frappe.app);
		});
	}

	if (document.body) showWelcome();
	else document.addEventListener("DOMContentLoaded", showWelcome);
})();
