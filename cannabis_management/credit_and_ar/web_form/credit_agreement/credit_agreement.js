frappe.ready(function () {
	// bind events here

	// Show the company name, centered, above the form title — mirrors the
	// boxed "[COMPANY NAME]" pill at the top of the Credit Agreement PDF.
	var $head = $(".web-form-head").first();
	if ($head.length && !$head.find(".ca-companyname").length) {
		$("<div>", {
			text: "MOTLEY TERPZ",
			class: "ca-companyname",
		}).prependTo($head);
	}

	// Pre-fill today's date on a new agreement. The web form's own
	// "default": "Today" mechanism (unlike Desk) never special-cases the
	// word "Today" — it stuffs that literal string into the field, which
	// then fails date validation and pops a "Date Today must be in format:
	// ..." error. Setting the real ISO value through the control here
	// avoids that entirely.
	if (frappe.web_form && frappe.web_form.is_new && frappe.web_form.fields_dict.agreement_date) {
		frappe.web_form.set_value("agreement_date", frappe.datetime.get_today());
	}

	// --- Attach a PDF of the filled-in agreement to the Credit Application
	// record the customer just created. --------------------------------------
	//
	// Neither html2canvas (captures the page) nor jsPDF (wraps that capture
	// in a PDF page) are part of the core asset bundle, so both are fetched
	// from this web form's own vendor folder the first time they're needed,
	// then reused for the rest of the page's life.
	var HTML2CANVAS_URL = "/assets/cannabis_management/js/vendor/html2canvas.min.js";
	var JSPDF_URL = "/assets/cannabis_management/js/vendor/jspdf.umd.min.js";

	function load_script(url, get_global) {
		var existing = get_global();
		if (existing) return Promise.resolve(existing);
		return new Promise(function (resolve, reject) {
			var script = document.createElement("script");
			script.src = url;
			script.onload = function () {
				resolve(get_global());
			};
			script.onerror = reject;
			document.head.appendChild(script);
		});
	}

	function load_html2canvas() {
		return load_script(HTML2CANVAS_URL, function () {
			return window.html2canvas;
		});
	}

	function load_jspdf() {
		return load_script(JSPDF_URL, function () {
			return window.jspdf && window.jspdf.jsPDF;
		});
	}

	// Warm both libraries up front so the actual submit isn't blocked on the
	// network fetch — by the time the customer clicks Submit, they're already
	// cached.
	Promise.all([load_html2canvas(), load_jspdf()]).catch(function () {
		/* if this fails we'll just retry (and no-op on failure) at submit time */
	});

	function canvas_to_pdf_blob(canvas) {
		var jsPDF = window.jspdf.jsPDF;
		// Page sized to exactly match the captured form (in mm, at 96dpi) so
		// the whole thing lands on one page with no cropping or scaling.
		var mm_per_px = 25.4 / 96;
		var width_mm = canvas.width * mm_per_px;
		var height_mm = canvas.height * mm_per_px;
		var pdf = new jsPDF({
			orientation: width_mm > height_mm ? "landscape" : "portrait",
			unit: "mm",
			format: [width_mm, height_mm],
		});
		// JPEG at 0.85 quality keeps the PDF a reasonable size — the form is
		// mostly flat white/gray with text, so the quality loss isn't visible,
		// and it avoids multi-MB PDFs from an uncompressed PNG embed.
		pdf.addImage(canvas.toDataURL("image/jpeg", 0.85), "JPEG", 0, 0, width_mm, height_mm);
		return pdf.output("blob");
	}

	function upload_pdf(blob, doctype, docname) {
		return new Promise(function (resolve, reject) {
			var xhr = new XMLHttpRequest();
			xhr.open("POST", "/api/method/upload_file", true);
			xhr.setRequestHeader("Accept", "application/json");
			xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
			xhr.onreadystatechange = function () {
				if (xhr.readyState === XMLHttpRequest.DONE) {
					xhr.status === 200 ? resolve(xhr) : reject(new Error(xhr.status));
				}
			};

			var form_data = new FormData();
			form_data.append("file", blob, "credit-agreement-" + docname + ".pdf");
			form_data.append("is_private", 1);
			form_data.append("folder", "Home");
			form_data.append("doctype", doctype);
			form_data.append("docname", docname);
			xhr.send(form_data);
		});
	}

	function capture_and_attach(doc) {
		var target = document.querySelector(".web-form-container");
		if (!target || !doc || !doc.name) return Promise.resolve();

		return Promise.all([load_html2canvas(), load_jspdf()])
			.then(function (libs) {
				return libs[0](target, {
					backgroundColor: "#ffffff",
					useCORS: true,
					scale: 1,
					logging: false,
				});
			})
			.then(function (canvas) {
				return upload_pdf(canvas_to_pdf_blob(canvas), doc.doctype || "Credit Application", doc.name);
			})
			.catch(function (err) {
				// The application itself has already been saved successfully —
				// a failed PDF attach should never surface as an error to the
				// customer, just a quiet console note for us.
				console.warn("Credit Agreement PDF attach failed:", err);
			});
	}

	// Wait for the WebForm controller to exist, then wrap handle_success so
	// we capture the form while it is still on screen. handle_success hides
	// the form and swaps in the success page, so the capture has to be
	// awaited (not just started) before letting that hide happen — otherwise
	// html2canvas clones a display:none, zero-size container.
	if (frappe.web_form && typeof frappe.web_form.handle_success === "function") {
		var original_handle_success = frappe.web_form.handle_success.bind(frappe.web_form);
		frappe.web_form.handle_success = function (data) {
			capture_and_attach(data).then(function () {
				original_handle_success(data);
			});
		};
	}
});
