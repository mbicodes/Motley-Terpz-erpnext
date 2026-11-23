// Team time off calendar: /app/time-off-request/view/calendar
frappe.views.calendar["Time Off Request"] = {
	field_map: {
		start: "from_date",
		end: "to_date",
		id: "name",
		title: "title",
		allDay: "all_day",
		color: "color",
		editable: "locked", // dragging would change dates without validation
		convertToUserTz: "no_tz",
	},
	get_events_method: "cannabis_management.time_clock.time_off.calendar_events",
};
