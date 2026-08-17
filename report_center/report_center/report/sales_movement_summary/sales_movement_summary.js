frappe.query_reports["Sales Movement Summary"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer"
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.delay_dispatch !== undefined && data.delay_dispatch !== null) {
			let color = "";
			let bg = "";
			if (data.delay_dispatch <= 3) {
				color = "#1e8a5b"; bg = "#e7f5ee";
			} else if (data.delay_dispatch > 3 && data.delay_dispatch <= 5) {
				color = "#856404"; bg = "#fff3cd";
			} else if (data.delay_dispatch > 5) {
				color = "#721c24"; bg = "#f8d7da";
			}
			if (color) {
				return `<span style="display:block; width:100%; height:100%; background-color:${bg}; color:${color}; padding: 2px;">${value}</span>`;
			}
		}
		return value;
	}
};
