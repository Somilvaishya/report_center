// MSME-1 is filed for Apr–Sep and Oct–Mar; default to the last half-year that has ended.
function last_half_year() {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const year = today.getFullYear();
	const month = today.getMonth() + 1;
	if (month >= 10) return [`${year}-04-01`, `${year}-09-30`];
	if (month >= 4) return [`${year - 1}-10-01`, `${year}-03-31`];
	return [`${year - 1}-04-01`, `${year - 1}-09-30`];
}

const [HALF_START, HALF_END] = last_half_year();

frappe.query_reports["MSME-1 Return"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: HALF_START,
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: HALF_END,
			reqd: 1,
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["MSME-1 Return", "Invoice-wise FIFO Detail"],
			default: "MSME-1 Return",
			reqd: 1,
		},
		{
			fieldname: "msme_type",
			label: __("MSME Type"),
			fieldtype: "Select",
			options: ["Micro & Small", "Micro", "Small"],
			default: "Micro & Small",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "ageing_based_on",
			label: __("45 Days Counted From"),
			fieldtype: "Select",
			options: ["Posting Date", "Supplier Invoice Date"],
			default: "Posting Date",
		},
		{
			fieldname: "reason",
			label: __("Reason for Delay (Column h)"),
			fieldtype: "Data",
			default: ".",
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Download MSME-1 Excel"), () => {
			const filters = report.get_values();
			if (!filters) return;
			open_url_post(
				frappe.urllib.get_full_url(
					"/api/method/report_center.report_center.report.msme_1_return.msme_1_return.download_msme_excel"
				),
				{ filters: JSON.stringify(filters) }
			);
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const late = ["late_no", "late_amt", "out_gt_no", "out_gt_amt", "paid_after"];
		if (late.includes(column.fieldname) && data[column.fieldname] > 0) {
			return `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		if (column.fieldname === "bucket" && data.bucket && data.age_days > 45) {
			return `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
