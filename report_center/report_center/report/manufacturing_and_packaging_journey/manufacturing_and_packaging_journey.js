frappe.query_reports["Manufacturing and Packaging Journey"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "view_mode",
			label: __("View Mode"),
			fieldtype: "Select",
			options: [
				"Hierarchical Journey Tree",
				"Batch Lineage Matrix",
				"Loose Item Reconciliation Summary"
			],
			default: "Hierarchical Journey Tree",
			reqd: 1,
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
			get_query: () => {
				const loose = frappe.query_report.get_filter_value("loose_item_code");
				const fg = frappe.query_report.get_filter_value("fg_item_code");
				const item = loose || fg;
				return { filters: item ? { item: item } : {} };
			},
		},
		{
			fieldname: "loose_item_code",
			label: __("Loose / Sub-Assembly Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "fg_item_code",
			label: __("Finished Good (Packaged) Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "rm_item_code",
			label: __("Raw Material Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "stock_entry",
			label: __("Stock Entry"),
			fieldtype: "Link",
			options: "Stock Entry",
			get_query: () => ({
				filters: { purpose: "Manufacture", docstatus: 1 }
			}),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "created_by",
			label: __("Created By (User)"),
			fieldtype: "Link",
			options: "User",
		},
	],

	tree: true,
	name_field: "journey",
	initial_depth: 2,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Format Stage/Journey tree column with styled modern badges
		if (column.fieldname === "journey") {
			if (data.stage_type === "Loose Produced") {
				return `<span style="display:inline-block; padding: 2px 8px; border-radius: 6px; background-color: var(--blue-100, #dbeafe); color: var(--blue-800, #1e40af); font-weight: 600;">${value}</span>`;
			} else if (data.stage_type === "RM Input") {
				return `<span style="display:inline-block; padding: 2px 6px; border-radius: 6px; background-color: var(--yellow-100, #fef3c7); color: var(--yellow-800, #92400e); font-weight: 500;">${value}</span>`;
			} else if (data.stage_type === "FG Produced") {
				return `<span style="display:inline-block; padding: 2px 8px; border-radius: 6px; background-color: var(--green-100, #d1fae5); color: var(--green-800, #065f46); font-weight: 600;">${value}</span>`;
			} else if (data.stage_type === "Loose Consumed") {
				return `<span style="display:inline-block; padding: 2px 6px; border-radius: 6px; background-color: var(--cyan-100, #cffafe); color: var(--cyan-800, #155e75); font-weight: 500;">${value}</span>`;
			} else if (data.stage_type === "Packaging Consumed") {
				return `<span style="display:inline-block; padding: 2px 6px; border-radius: 6px; background-color: var(--purple-100, #f3e8ff); color: var(--purple-800, #6b21a8); font-weight: 500;">${value}</span>`;
			}
		}

		// Highlight Batch No
		if (column.fieldname === "batch_no" || column.fieldname === "loose_batch_no" || column.fieldname === "fg_batch_no") {
			if (data[column.fieldname]) {
				return `<span style="font-weight: 600; color: var(--primary-color, #171717);">${value}</span>`;
			}
		}

		// Highlight Warehouse Stock
		if (column.fieldname === "current_batch_qty" || column.fieldname === "current_wh_qty" || column.fieldname === "current_wh_stock") {
			const qty = flt(data[column.fieldname]);
			if (qty <= 0) {
				return `<span style="color: var(--text-muted, #737373);">${value}</span>`;
			} else {
				return `<span style="font-weight: 600; color: var(--green-700, #047857);">${value}</span>`;
			}
		}

		// Highlight Discrepancy / Variance
		if (column.fieldname === "stock_discrepancy") {
			const disc = flt(data.stock_discrepancy);
			if (disc > 0) {
				return `<span style="color: var(--red-600, #dc2626); font-weight: 600;">${value} (Shortage)</span>`;
			} else if (disc < 0) {
				return `<span style="color: var(--blue-600, #2563eb); font-weight: 600;">${value} (Surplus)</span>`;
			}
		}

		return value;
	},
};
