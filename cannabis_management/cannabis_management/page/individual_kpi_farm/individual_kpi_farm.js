frappe.pages['individual-kpi-farm'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Individual KPI — Farm',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getIkpiHTML());
	var root = wrapper.querySelector('.ikpi-dash');

	var API = 'cannabis_management.api.individual_kpi_farm.';
	var currentEmployee = null;
	var fromDate = frappe.datetime.add_months(frappe.datetime.get_today(), -1);
	var toDate = frappe.datetime.get_today();

	root.querySelector('#ikpi-from-date').value = fromDate;
	root.querySelector('#ikpi-to-date').value = toDate;

	root.querySelector('#ikpi-employee-select').addEventListener('change', function (e) {
		currentEmployee = e.target.value;
		loadEmployee(currentEmployee);
	});

	root.querySelector('#ikpi-apply-range').addEventListener('click', function () {
		fromDate = root.querySelector('#ikpi-from-date').value || fromDate;
		toDate = root.querySelector('#ikpi-to-date').value || toDate;
		if (currentEmployee) loadEmployee(currentEmployee);
	});

	loadEmployeeOptions();

	function loadEmployeeOptions() {
		frappe.call({
			method: API + 'get_employee_options',
			callback: function (r) {
				var rows = r.message || [];
				var $select = root.querySelector('#ikpi-employee-select');
				if (!rows.length) {
					$select.innerHTML = '<option value="">No profiles configured</option>';
					root.querySelector('#ikpi-body').innerHTML =
						'<div class="ikpi-empty">No Farm Employee KPI Profile records exist yet. Create one to populate this page.</div>';
					return;
				}
				$select.innerHTML = rows.map(function (r) {
					return '<option value="' + frappe.utils.escape_html(r.employee) + '">' +
						frappe.utils.escape_html(r.label) + '</option>';
				}).join('');
				currentEmployee = rows[0].employee;
				loadEmployee(currentEmployee);
			},
		});
	}

	function loadEmployee(employee) {
		frappe.call({
			method: API + 'get_profile',
			args: { employee: employee },
			callback: function (r) {
				var profile = r.message;
				if (!profile) {
					root.querySelector('#ikpi-body').innerHTML = '<div class="ikpi-empty">No profile found for this employee.</div>';
					return;
				}
				frappe.call({
					method: API + 'get_actuals',
					args: { employee: employee, from_date: fromDate, to_date: toDate },
					callback: function (ar) {
						render(root, profile, ar.message || {});
					},
				});
			},
		});
	}

	function render(root, profile, actuals) {
		root.querySelector('#ikpi-hdr-name').textContent = profile.employee_name || profile.employee;
		root.querySelector('#ikpi-name').textContent = profile.employee_name || profile.employee;
		root.querySelector('#ikpi-role').textContent = profile.role_title || '';

		var metaParts = [];
		if (profile.reports_to) metaParts.push('Reports to: ' + profile.reports_to);
		if (profile.employment_type) metaParts.push(profile.employment_type);
		metaParts.push('TSBC Ranch LLC — Farm');
		root.querySelector('#ikpi-meta').innerHTML = metaParts
			.map(function (p) { return frappe.utils.escape_html(p); })
			.join(' <span class="ikpi-meta-sep">·</span> ');

		var $note = root.querySelector('#ikpi-note');
		if (profile.note) {
			$note.style.display = '';
			$note.innerHTML = '<span>⚠</span><span><strong>Note:</strong> ' + frappe.utils.escape_html(profile.note) + '</span>';
		} else {
			$note.style.display = 'none';
		}

		var responsibilities = profile.responsibilities || [];
		root.querySelector('#ikpi-responsibilities').innerHTML = responsibilities.length
			? responsibilities.map(function (r) { return '<li>' + frappe.utils.escape_html(r) + '</li>'; }).join('')
			: '<div class="ikpi-empty">No responsibilities listed.</div>';

		var kpiRows = profile.kpi_targets || [];
		root.querySelector('#ikpi-kpi-table-body').innerHTML = kpiRows.length
			? kpiRows.map(function (row) { return kpiRowHTML(row, actuals); }).join('')
			: '<tr><td colspan="4" class="ikpi-empty">No KPIs configured.</td></tr>';

		var $cadence = root.querySelector('#ikpi-cadence');
		if (profile.performance_review_cadence) {
			$cadence.style.display = '';
			$cadence.querySelector('.ikpi-cadence-body').textContent = profile.performance_review_cadence;
		} else {
			$cadence.style.display = 'none';
		}
	}

	function kpiRowHTML(row, actuals) {
		var actualHTML;
		if (row.backend_key && actuals[row.backend_key] !== undefined && actuals[row.backend_key] !== null) {
			actualHTML = '<span class="ikpi-actual">' + frappe.utils.escape_html(String(actuals[row.backend_key])) +
				(row.suffix || '') + '</span>';
		} else {
			actualHTML = '<span class="ikpi-actual ikpi-nottracked">Not Tracked Yet</span>';
		}

		return '\
<tr>\
  <td class="ikpi-kpi-name">' + frappe.utils.escape_html(row.kpi_label || '') + '</td>\
  <td class="ikpi-target">' + frappe.utils.escape_html(row.target || '—') + '</td>\
  <td>' + actualHTML + '</td>\
  <td class="ikpi-how-measured">' + frappe.utils.escape_html(row.how_measured || '') + '</td>\
</tr>';
	}

	function getIkpiHTML() {
		return '\
<div class="ikpi-dash">\
  <div class="ikpi-filter-bar">\
    <label style="font-size:12px;">Employee</label>\
    <select class="form-control input-sm" id="ikpi-employee-select" style="width:220px;"></select>\
    <label style="font-size:12px;">From</label>\
    <input type="date" id="ikpi-from-date" class="form-control input-sm" style="width:150px;">\
    <label style="font-size:12px;">To</label>\
    <input type="date" id="ikpi-to-date" class="form-control input-sm" style="width:150px;">\
    <button class="btn btn-xs btn-primary" id="ikpi-apply-range">Apply</button>\
  </div>\
\
  <div class="ikpi-header">\
    <div class="ikpi-hdr-left">TSBC Ranch LLC — Farm — Individual KPIs &amp; Responsibilities</div>\
    <div class="ikpi-hdr-right" id="ikpi-hdr-name"></div>\
  </div>\
\
  <div id="ikpi-body">\
    <div class="ikpi-name" id="ikpi-name"></div>\
    <div class="ikpi-role" id="ikpi-role"></div>\
    <div class="ikpi-meta" id="ikpi-meta"></div>\
    <div class="ikpi-note" id="ikpi-note" style="display:none;"></div>\
\
    <div class="ikpi-columns">\
      <div>\
        <div class="ikpi-section-title">RESPONSIBILITIES</div>\
        <ul class="ikpi-responsibilities" id="ikpi-responsibilities"></ul>\
      </div>\
      <div>\
        <div class="ikpi-section-title">KPIS &amp; TARGETS</div>\
        <table class="ikpi-table">\
          <thead>\
            <tr><th>KPI</th><th>Target</th><th>Actual</th><th>How measured</th></tr>\
          </thead>\
          <tbody id="ikpi-kpi-table-body"></tbody>\
        </table>\
      </div>\
    </div>\
\
    <div class="ikpi-cadence" id="ikpi-cadence" style="display:none;">\
      <div class="ikpi-cadence-title">HOW PERFORMANCE IS MEASURED</div>\
      <div class="ikpi-cadence-body"></div>\
    </div>\
  </div>\
</div>';
	}
};
