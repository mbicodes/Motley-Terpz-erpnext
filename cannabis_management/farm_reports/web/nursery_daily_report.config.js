/* =====================================================================
   CONFIG: Nursery Daily Report (Gus)
   Field names below must match the DocType. Change them here if your
   DocType uses different fieldnames.
   ===================================================================== */
var YN = ['Yes', 'No'];

window.DR_CONFIG = {
    doctype: 'Nursery Daily Report',
    route: 'nursery-daily-report',
    site: 'TSBC Nursery',
    title: 'Nursery Daily Report',
    intro: 'Answer each question for today. Follow-up questions appear based on your answers.',
    submitLabel: 'Submit report',
    submitOnSave: true,
    dateField: 'report_date',
    userField: 'submitted_by',
    activityUnit: 'Plants',
    previewUser: 'Gus (preview)',
    previewNote: 'Preview mode: this page is not connected to ERPNext. Submitting shows the data that would be saved.',

    /* Child table fieldnames */
    child: { photo: 'photo' },   // Daily Report Photo

    sources: {},
    previewLists: {},

    sections: [
        {
            title: 'Watering',
            questions: [
                { field: 'nursery_watered', type: 'choice', label: 'Was the nursery watered today?', options: YN, required: true },
                { field: 'watering_notes', type: 'text', label: 'Watering notes', placeholder: 'Anything worth noting about today’s watering' }
            ]
        },
        {
            title: 'Nutrients and sprays',
            questions: [
                { field: 'sprays_applied', type: 'choice', label: 'Were nutrients, sprays or other IPM applied in the nursery today?', options: YN, required: true },
                { field: 'spray_mixture_details', type: 'text', label: 'What was applied, with mixture details', placeholder: 'Product, amount and water volume', required: true,
                  showIf: function (s) { return s.sprays_applied === 'Yes'; } }
            ]
        },
        {
            title: 'Male scouting',
            questions: [
                { field: 'scouted_for_males', type: 'choice', label: 'Did you scout for males today?', options: YN, required: true },
                { field: 'males_found', type: 'choice', label: 'Were any males found?', options: YN, required: true,
                  showIf: function (s) { return s.scouted_for_males === 'Yes'; } },
                { field: 'male_photos', type: 'photos', label: 'Photos of the males found', required: true,
                  showIf: function (s) { return s.males_found === 'Yes'; } },
                { field: 'next_scouting_date', type: 'date', label: 'When do you plan to scout again?', required: true,
                  showIf: function (s) { return s.scouted_for_males === 'No'; } }
            ]
        },
        {
            title: 'METRC',
            questions: [
                { field: 'plants_tagged_per_metrc', type: 'choice', label: 'Are all plants in the nursery and outdoor farm tagged per METRC?', options: YN, required: true,
                  help: 'All mature plants have individual tags and all immature plants are on package tags.' },
                { field: 'pending_tagging_actions', type: 'text', label: 'What needs to get done?', placeholder: 'Which plants or areas still need tags', required: true,
                  showIf: function (s) { return s.plants_tagged_per_metrc === 'No'; } },
                { field: 'promised_completion_date', type: 'date', label: 'Promised completion date', required: true,
                  showIf: function (s) { return s.plants_tagged_per_metrc === 'No'; } }
            ]
        }
    ]
};
