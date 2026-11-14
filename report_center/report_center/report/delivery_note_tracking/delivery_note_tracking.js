// Copyright (c) 2026, Report Center and contributors
// For license information, please see license.txt

frappe.query_reports["Delivery Note Tracking"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: [
				{ value: "Tree", label: __("Tree View") },
				{ value: "Normal", label: __("Normal View") },
			],
			default: "Tree",
			reqd: 1,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "delivery_note",
			label: __("Delivery Note"),
			fieldtype: "Link",
			options: "Delivery Note",
			get_query: () => {
				const { company, customer } = frappe.query_report.get_filter_values();
				const filters = { docstatus: 1 };
				if (company) filters.company = company;
				if (customer) filters.customer = customer;
				return { filters };
			},
		},
		{
			fieldname: "dn_status",
			label: __("DN Status"),
			fieldtype: "Select",
			options: [""],
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "location",
			label: __("Billing Location-From"),
			fieldtype: "Link",
			options: "Location",
		},
	],

	tree: true,
	name_field: "delivery_note",
	parent_field: "parent_delivery_note",
	initial_depth: 0,

	onload(report) {
		frappe
			.xcall(
				"report_center.report_center.report.delivery_note_tracking.delivery_note_tracking.get_dn_statuses"
			)
			.then((statuses) => {
				const filter = report.get_filter("dn_status");
				filter.df.options = ["", ...(statuses || [])];
				filter.refresh();
			});

		// Frappe's export keeps only the rows open on screen, so a collapsed tree would export
		// DN rows alone, and item rows carry no DN number. The tree view therefore exports the
		// normal view: every row complete. The normal view keeps Frappe's own export.
		// The query report object is shared by every report, so wrap once and only act for this one.
		if (!report.__dn_tracking_export) {
			report.__dn_tracking_export = report.export_report;
			report.export_report = function () {
				if (this.report_name !== "Delivery Note Tracking" || this.get_filter_value("view") === "Normal") {
					return this.__dn_tracking_export();
				}
				return export_normal_view(this);
			};
		}
	},

	formatter(value, row, column, data, default_formatter) {
		// "Pending" and "2 Invoices" sit in the Sales Invoice column but aren't documents
		if (column.fieldname === "sales_invoice" && data && (value === __("Pending") || / Invoices$/.test(value || ""))) {
			const color = value === __("Pending") ? "var(--orange-600)" : "var(--text-muted)";
			return `<span style="color:${color}">${frappe.utils.escape_html(value)}</span>`;
		}
		value = default_formatter(value, row, column, data);
		if (data && data.indent === 0 && column.fieldname === "delivery_note") {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};

function export_normal_view(report) {
	const dialog = frappe.report_utils.get_export_dialog(
		__(report.report_name),
		[{ label: __("Include filters"), fieldname: "include_filters", fieldtype: "Check" }],
		({ file_format, include_filters, export_in_background, csv_delimiter, csv_quoting, csv_decimal_sep }) => {
			report.make_access_log("Export", file_format);
			const filters = { ...report.get_filter_values(true), view: "Normal" };
			const args = {
				cmd: "frappe.desk.query_report.export_query",
				report_name: report.report_name,
				custom_columns: report.custom_columns?.length ? report.custom_columns : [],
				file_format_type: file_format,
				filters,
				applied_filters: report.get_applied_filters(filters),
				// every row of the report, not just the ones open on screen
				visible_idx: [],
				ignore_visible_idx: 1,
				csv_delimiter,
				csv_quoting,
				csv_decimal_sep,
				include_filters,
				export_in_background,
			};
			if (export_in_background) {
				frappe.call({ method: args.cmd, args });
			} else {
				open_url_post(frappe.request.url, args);
			}
			dialog.hide();
		}
	);
	dialog.show();
}
