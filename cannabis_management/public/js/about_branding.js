(function () {
	const WEBSITE = "https://alltechvirtual.com";
	const HIDDEN_LINKS = [
		"https://github.com/frappe",
		"https://frappe.io/blog",
		"https://discuss.frappe.io",
		"https://linkedin.com/company/frappe-tech",
		"https://x.com/frappetech",
		"https://www.youtube.com/@frappetech",
		"https://www.instagram.com/frappetech",
	];

	frappe.provide("frappe.ui.misc");
	const frappe_about = frappe.ui.misc.about;
	if (!frappe_about) return;

	frappe.ui.misc.about = function () {
		const built_now = !frappe.ui.misc.about_dialog;
		const result = frappe_about.apply(this, arguments);
		if (built_now && frappe.ui.misc.about_dialog) {
			const $body = $(frappe.ui.misc.about_dialog.body);
			$body.find("a[href='https://frappe.io/']").attr("href", WEBSITE).text(WEBSITE);
			HIDDEN_LINKS.forEach((href) => $body.find(`a[href='${href}']`).closest("p").remove());
		}
		return result;
	};
})();
