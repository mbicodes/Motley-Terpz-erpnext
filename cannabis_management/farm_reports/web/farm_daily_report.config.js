/* =====================================================================
   CONFIG: Farm Daily Report (Joe)
   Field names below must match the DocType. Change them here if your
   DocType uses different fieldnames.
   ===================================================================== */
var YNA = ['Yes', 'No', 'N/A (No plants in ground)'];
var YN = ['Yes', 'No'];

window.DR_CONFIG = {
    doctype: 'Farm Daily Report',
    route: 'farm-daily-report',
    site: 'TSBC Outdoor Farm',
    title: 'Farm Daily Report',
    intro: 'Answer each question for today. Follow-up questions appear based on your answers.',
    submitLabel: 'Submit report',
    submitOnSave: true,
    dateField: 'report_date',
    userField: 'submitted_by',
    activityUnit: 'Plants',
    previewUser: 'Joe (preview)',
    previewNote: 'Preview mode: this page is not connected to ERPNext. Submitting shows the data that would be saved.',

    /* Child table fieldnames */
    child: {
        photo: 'photo',                     // Daily Report Photo
        flc: 'flc', laborers: 'no_of_laborers',   // Daily Report FLC Labor
        activity: 'activity', people: 'no_of_people', quantity: 'quantity_completed',
        uom: 'uom', perPerson: 'output_per_person'  // Daily Report Activity
    },

    /* Where dropdown lists come from. A `method` source calls a whitelisted
       method that returns [{value, label}]; the FLC list uses one so reporters
       need no read permission on Supplier. */
    sources: {
        flc: { method: 'cannabis_management.farm_reports.api.get_flc_suppliers' },
        activity: { doctype: 'Farm Activity', value: 'name', label: 'name', filters: [['disabled', '=', 0]] }
    },
    previewLists: {
        flc: ['ATD Consulting Limited- Sabor', 'Sample Contractor'],
        activity: ['Tagging', 'Deleafing', 'Watering', 'Weeding', 'Topping']
    },

    sections: [
        {
            title: 'Watering',
            description: 'Mark each block for today.',
            questions: [
                { field: 'left_block_watered', type: 'choice', label: 'Left block watered', options: YNA, required: true },
                { field: 'middle_block_watered', type: 'choice', label: 'Middle block watered', options: YNA, required: true },
                { field: 'right_block_watered', type: 'choice', label: 'Right block watered', options: YNA, required: true },
                { field: 'watering_notes', type: 'text', label: 'Watering notes', placeholder: 'Anything worth noting about today’s watering' }
            ]
        },
        {
            title: 'IPM and sprays',
            description: 'If a section was sprayed, list the exact mixture with measurements.',
            questions: [
                { field: 'left_section_ipm', type: 'choice', label: 'Left section sprayed', options: YNA, required: true },
                { field: 'left_ipm_mixture_details', type: 'text', label: 'Left section mixture and measurements', placeholder: 'Product, amount and water volume', required: true,
                  showIf: function (s) { return s.left_section_ipm === 'Yes'; } },
                { field: 'middle_section_ipm', type: 'choice', label: 'Middle section sprayed', options: YNA, required: true },
                { field: 'middle_ipm_mixture_details', type: 'text', label: 'Middle section mixture and measurements', placeholder: 'Product, amount and water volume', required: true,
                  showIf: function (s) { return s.middle_section_ipm === 'Yes'; } },
                { field: 'right_section_ipm', type: 'choice', label: 'Right section sprayed', options: YNA, required: true },
                { field: 'right_ipm_mixture_details', type: 'text', label: 'Right section mixture and measurements', placeholder: 'Product, amount and water volume', required: true,
                  showIf: function (s) { return s.right_section_ipm === 'Yes'; } }
            ]
        },
        {
            title: 'Male scouting',
            questions: [
                { field: 'scouted_for_males', type: 'choice', label: 'Did you scout for males today?', options: YNA, required: true },
                { field: 'males_found', type: 'choice', label: 'Did you find any males?', options: YN, required: true,
                  showIf: function (s) { return s.scouted_for_males === 'Yes'; } },
                { field: 'male_photos', type: 'photos', label: 'Photos of the males found', required: true,
                  showIf: function (s) { return s.males_found === 'Yes'; } },
                { field: 'planned_scouting_date', type: 'date', label: 'When do you plan to scout?', required: true,
                  showIf: function (s) { return s.scouted_for_males === 'No'; } }
            ]
        },
        {
            title: 'Farm management',
            questions: [
                { field: 'weeds_under_control', type: 'choice', label: 'Are the weeds under control?', options: YN, required: true },
                { field: 'weed_control_plan_date', type: 'date', label: 'When will you tackle the weeds?', required: true,
                  showIf: function (s) { return s.weeds_under_control === 'No'; } },
                { field: 'weed_control_plan_notes', type: 'text', label: 'Weed control plan', placeholder: 'Which areas and how',
                  showIf: function (s) { return s.weeds_under_control === 'No'; } },
                { field: 'maintenance_notes', type: 'text', label: 'General maintenance notes', placeholder: 'Irrigation repairs, fencing, equipment and similar' }
            ]
        },
        {
            title: 'Labor',
            questions: [
                { field: 'flc_workers_on_farm', type: 'choice', label: 'Were any FLC workers on the farm today?', options: YN, required: true },
                { field: 'flc_labor', type: 'flc_table', label: 'Contractors and headcount', totalField: 'total_laborers', required: true,
                  help: 'Add each contractor and how many laborers they sent today.',
                  showIf: function (s) { return s.flc_workers_on_farm === 'Yes'; } },
                { field: 'activities', type: 'activity_table', label: 'Activities and production', required: true,
                  help: 'Split the day’s labor by activity. For example, 50 people tagged 5,000 plants.',
                  showIf: function (s) { return s.flc_workers_on_farm === 'Yes'; } }
            ]
        },
        {
            title: 'Other',
            questions: [
                { field: 'other_notes', type: 'text', label: 'Other notes, comments or concerns', placeholder: 'Anything else the team should know about today' },
                { field: 'photos', type: 'photos', label: 'Photos from today' }
            ]
        }
    ]
};
