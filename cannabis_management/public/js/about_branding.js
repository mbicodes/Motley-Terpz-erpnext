// About dialog: the "Website" line points at All Tech Virtual instead of
// frappe.io. Frappe's about.js hard-codes that link in the dialog's HTML (it is
// not translatable text), so the link is swapped right after the dialog is
// built. The app title and the © line are handled server-side in branding/.
(function () {
	const WEBSITE = "https://alltechvirtual.com";

	frappe.provide("frappe.ui.misc");
	const frappe_about = frappe.ui.misc.about;
	if (!frappe_about) return;

	frappe.ui.misc.about = function () {
		const built_now = !frappe.ui.misc.about_dialog;
		const result = frappe_about.apply(this, arguments);
		if (built_now && frappe.ui.misc.about_dialog) {
			$(frappe.ui.misc.about_dialog.body)
				.find("a[href='https://frappe.io/']")
				.attr("href", WEBSITE)
				.text(WEBSITE);
		}
		return result;
	};
})();
