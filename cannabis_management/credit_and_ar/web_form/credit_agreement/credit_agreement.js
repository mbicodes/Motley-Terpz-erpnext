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

	// Sales Rep and Payment Terms are excluded/filtered server-side, in
	// credit_agreement.py's get_context — NOT here. Web forms turn every
	// Link field into an "Autocomplete" backed by a static, pre-baked
	// option list (see WebForm.load_form_data / get_link_options); setting
	// df.get_query on that control makes it call a server *method* instead
	// (df.get_query = {query, params}, not Desk's {filters: {...}}), so a
	// Link-style filters object here just empties the list — it doesn't
	// narrow it. Filtering the baked-in options string before render is
	// the only thing that actually works for this fieldtype.

	// Match the printed agreement's "Label:" style. This has to be real text
	// appended after the label, not a CSS ::after — Frappe already puts the
	// red required-asterisk on .control-label via ::after (controls.scss),
	// and only one ::after can win per element.
	$(".web-form-wrapper .control-label").each(function () {
		var $label = $(this);
		if (!/:\s*$/.test($label.text())) {
			$label.append(":");
		}
	});

	// The PDF attached to the record on submit is rendered server-side from
	// the "Credit Agreement" Print Format (see
	// cannabis_management.credit_and_ar.web_form_intake.after_insert) — a
	// clean copy of the printed agreement filled with the values the client
	// just submitted, not a screenshot of this web page. Nothing to do here.
});
