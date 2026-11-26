(function () {
	"use strict";

	if (!/^\/app(\/|$)/.test(location.pathname)) return;

	var BOOT_TIMEOUT_MS = 15000;
	var STARTUP_WINDOW_MS = 30000;
	var RELOAD_GUARD_MS = 180000;
	var RELOAD_KEY = "mlt-desk-auto-reload-at";
	var REPORT_URL = "/api/method/cannabis_management.desk_health.report";

	var startedAt = Date.now();
	var errors = [];
	var failedResources = [];
	var reportedUndefined = false;

	function short(text, n) {
		text = text == null ? "" : String(text);
		return text.length > n ? text.slice(0, n) + "…" : text;
	}

	function elementPath(el) {
		var parts = [];
		for (var i = 0; el && el.nodeType === 1 && i < 7; i++, el = el.parentElement) {
			var part = el.tagName.toLowerCase();
			if (el.id) part += "#" + el.id;
			var cls = (el.getAttribute("class") || "").trim().split(/\s+/).slice(0, 3).join(".");
			if (cls) part += "." + cls;
			parts.unshift(part);
		}
		return parts.join(" > ");
	}

	function send(kind, details) {
		try {
			var token = (window.frappe && (frappe.csrf_token || (frappe.boot && frappe.boot.csrf_token))) || "";
			fetch(REPORT_URL, {
				method: "POST",
				credentials: "same-origin",
				keepalive: true,
				headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": token },
				body: JSON.stringify({ kind: kind, details: details }),
			}).catch(function () {});
		} catch (e) {}
	}

	function context() {
		var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
		return {
			path: location.pathname + location.search,
			since_load_ms: Date.now() - startedAt,
			route: window.frappe && frappe.get_route_str ? short(frappe.get_route_str(), 200) : null,
			splash_present: !!document.querySelector(".splash"),
			container_ready: !!(window.frappe && frappe.container),
			page_ready: pageReady(),
			freeze_shown: !!document.querySelector("#freeze.in, .freeze-message-container"),
			timing: nav ? {
				response_end: Math.round(nav.responseEnd),
				dom_content_loaded: Math.round(nav.domContentLoadedEventEnd),
				load: Math.round(nav.loadEventEnd),
			} : null,
			errors: errors.slice(-10),
			failed_resources: failedResources.slice(-10),
		};
	}

	function pageReady() {
		var page = window.frappe && frappe.container && frappe.container.page;
		return !!(page && page.isConnected && (page.offsetWidth || page.offsetHeight || page.getClientRects().length));
	}

	function reportUndefined(el, url) {
		if (reportedUndefined) return;
		reportedUndefined = true;
		send("undefined_url", {
			signature: "undefined_url",
			url: url,
			tag: el && el.tagName,
			element: el && el.outerHTML ? short(el.outerHTML, 800) : null,
			parent_path: el ? elementPath(el) : null,
			route: location.pathname,
		});
	}

	window.addEventListener("error", function (event) {
		var target = event.target;
		if (target && target !== window && target.nodeType === 1) {
			var url = target.currentSrc || target.src || target.href || "";
			if (typeof url !== "string") url = "";
			failedResources.push({ tag: target.tagName, url: short(url, 300) });
			if (/\/undefined$/.test(url.split("?")[0])) reportUndefined(target, url);
			return;
		}
		var item = {
			message: short(event.message, 300),
			source: short(event.filename, 200),
			line: event.lineno,
			col: event.colno,
			stack: short(event.error && event.error.stack, 1500),
			at_ms: Date.now() - startedAt,
		};
		errors.push(item);
		if (item.at_ms <= STARTUP_WINDOW_MS) {
			send("startup_error", Object.assign({ signature: item.message + "@" + item.source + ":" + item.line }, item, { path: location.pathname }));
		}
	}, true);

	window.addEventListener("unhandledrejection", function (event) {
		var reason = event.reason || {};
		errors.push({
			message: short(reason.message || reason, 300),
			stack: short(reason.stack, 1500),
			at_ms: Date.now() - startedAt,
			kind: "unhandledrejection",
		});
	});

	if (window.PerformanceObserver) {
		try {
			new PerformanceObserver(function (list) {
				list.getEntries().forEach(function (entry) {
					if (reportedUndefined || !/\/undefined$/.test(String(entry.name).split("?")[0])) return;
					var match = document.querySelector('[src="undefined"], [href="undefined"], [poster="undefined"], [data="undefined"], source[src="undefined"]');
					reportUndefined(match, entry.name + " (initiator: " + entry.initiatorType + ")");
				});
			}).observe({ type: "resource", buffered: true });
		} catch (e) {}
	}

	function showRecoveryNotice() {
		if (document.getElementById("mlt-desk-recover")) return;
		var box = document.createElement("div");
		box.id = "mlt-desk-recover";
		box.setAttribute("role", "alert");
		box.style.cssText = "position:fixed;inset:0;z-index:2147483600;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;" +
			"background:#12061f;color:#f6efff;font:500 18px/1.4 'Outfit','Segoe UI',system-ui,sans-serif;text-align:center;padding:24px;";
		box.innerHTML = "<div>MotleyERP didn't finish loading.</div>" +
			"<button type='button' style='font:600 16px/1 inherit;padding:14px 26px;border:0;border-radius:12px;background:#8d3fd6;color:#fff;cursor:pointer'>Reload</button>";
		box.querySelector("button").addEventListener("click", function () { location.reload(); });
		(document.body || document.documentElement).appendChild(box);
	}

	function checkBoot() {
		if (!document.querySelector(".splash") && pageReady()) return;
		if (document.visibilityState === "hidden") {
			document.addEventListener("visibilitychange", function retry() {
				if (document.visibilityState !== "visible") return;
				document.removeEventListener("visibilitychange", retry);
				setTimeout(checkBoot, 3000);
			});
			return;
		}

		var details = context();
		details.signature = "stuck_boot";
		send("stuck_boot", details);

		var last = 0;
		try { last = Number(sessionStorage.getItem(RELOAD_KEY) || 0); } catch (e) {}
		if (Date.now() - last > RELOAD_GUARD_MS) {
			try { sessionStorage.setItem(RELOAD_KEY, String(Date.now())); } catch (e) {}
			setTimeout(function () { location.reload(); }, 400);
		} else {
			showRecoveryNotice();
		}
	}

	setTimeout(checkBoot, BOOT_TIMEOUT_MS);
})();
