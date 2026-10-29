frappe.ready(function() {

	var $head = $(".web-form-head").first();
	if ($head.length && !$head.find(".ca-logo").length) {
		$("<img>", {
			src: "/assets/infix_theme/images/logo.png",
			alt: "",
			class: "ca-logo"
		}).prependTo($head);
	}
})
