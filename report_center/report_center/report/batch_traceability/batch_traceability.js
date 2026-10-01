const STAGE_COLORS = {
	"Received from Supplier": "var(--blue-600)",
	"Transferred": "var(--gray-600)",
	"Consumed in Production": "var(--orange-600)",
	"Produced": "var(--green-600)",
	"Dispatched to Customer": "var(--purple-600)",
	"Returned to Supplier": "var(--red-600)",
	"Returned by Customer": "var(--red-600)",
};

frappe.query_reports["Batch Traceability"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: ["Forward", "Backward"],
			default: "Forward",
			description: __("Forward: raw material batch to customer. Backward: finished batch to supplier."),
			reqd: 1,
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			description: __("Leave empty to see every item."),
			get_query: () => ({ filters: { has_batch_no: 1 } }),
			on_change: () => {
				frappe.query_report.set_filter_value("batch_no", "");
			},
		},
		{
			fieldname: "batch_no",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
			get_query: () => {
				const item_code = frappe.query_report.get_filter_value("item_code");
				return { filters: item_code ? { item: item_code } : {} };
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			description: __("Shows batches first received or produced in this period."),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],

	tree: true,
	name_field: "journey",
	initial_depth: 99,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data || column.fieldname !== "journey") return value;

		if (data.is_batch) return `<b>${value}</b>`;
		const color = STAGE_COLORS[data.journey];
		return color ? `<span style="color: ${color}; font-weight: 500">${value}</span>` : value;
	},
};
