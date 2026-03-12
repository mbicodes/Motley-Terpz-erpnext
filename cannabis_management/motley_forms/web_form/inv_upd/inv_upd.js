frappe.ready(function() {
    // Auto-set current user and make read only
    if (frappe.session.user && frappe.session.user !== 'Guest') {
        frappe.web_form.set_value('user', frappe.session.user);

        // Make the field read only after a short delay to ensure form is loaded
        setTimeout(function() {
            frappe.web_form.set_df_property('user', 'read_only', 1);

            // Also grey out the field visually
            var userField = document.querySelector('[data-fieldname="user"] input');
            if (userField) {
                userField.style.backgroundColor = '#f5f5f5';
                userField.style.cursor = 'not-allowed';
            }
        }, 500);
    }
});