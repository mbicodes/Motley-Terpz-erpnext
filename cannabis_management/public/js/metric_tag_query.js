// Shared Link-query filter for every Source/Target/Rejected Muid (Metric Tag)
// field. Every Warehouse and every Metric Tag carries a License
// (custom_license); a tag can only move through a warehouse that shares its
// License, so this restricts the field's dropdown to tags whose License
// matches the warehouse picked in that same row. See
// custom/metric_tag.py:tags_for_warehouse for the server side of the match.
//
// Must load before the Stock Entry / Purchase Receipt / Purchase Invoice /
// Delivery Note / Sales Invoice form scripts, which call
// cannabis_management.metric_tag.filter_by_warehouse() below.
window.cannabis_management = window.cannabis_management || {};
cannabis_management.metric_tag = {
    // query_path: dotted path of the whitelisted query method to use.
    // Defaults to the plain (no status restriction) query; the Source/Target
    // Tags fields pass the dedicated source_tags_for_warehouse /
    // target_tags_for_warehouse paths instead, which hardcode the status
    // restriction server-side so it can never be dropped client-side.
    filter_by_warehouse(
        frm,
        tag_field,
        warehouse_field,
        child_table = "items",
        query_path = "cannabis_management.cannabis_management.custom.metric_tag.tags_for_warehouse"
    ) {
        frm.set_query(tag_field, child_table, function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            return {
                query: query_path,
                filters: { warehouse: row[warehouse_field] },
            };
        });
    },
};
