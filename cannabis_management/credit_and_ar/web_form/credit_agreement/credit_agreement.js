frappe.ready(function () {

	var $head = $(".web-form-head").first();
	if ($head.length && !$head.find(".ca-companyname").length) {
		$("<div>", {
			text: "MOTLEY TERPZ",
			class: "ca-companyname",
		}).prependTo($head);
	}

	if (frappe.web_form && frappe.web_form.is_new && frappe.web_form.fields_dict.agreement_date) {
		frappe.web_form.set_value("agreement_date", frappe.datetime.get_today());
	}

	$(".web-form-wrapper .control-label").each(function () {
		var $label = $(this);
		if (!/:\s*$/.test($label.text())) {
			$label.append(":");
		}
	});

});
