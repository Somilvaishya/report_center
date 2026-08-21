// Copyright (c) 2026, Antigravity and contributors
// For license information, please see license.txt

// Dynamically load the standard General Ledger script synchronously
if (!frappe.query_reports["General Ledger"]) {
	$.ajax({
		url: "/api/method/frappe.desk.query_report.get_script",
		data: { report_name: "General Ledger" },
		dataType: "json",
		async: false,
		success: function(r) {
			if (r && r.message && r.message.script) {
				frappe.dom.eval(r.message.script);
			}
		}
	});
}

frappe.query_reports["General Ledger Audit"] = {
	filters: frappe.query_reports["General Ledger"] ? frappe.query_reports["General Ledger"].filters : [],

	onload: function(report) {
		// Add accounting dimensions dynamically
		if (erpnext.utils && erpnext.utils.add_dimensions) {
			erpnext.utils.add_dimensions("General Ledger Audit", 15);
		}

		// Call standard General Ledger onload behaviors (like buttons and links)
		if (frappe.query_reports["General Ledger"] && frappe.query_reports["General Ledger"].onload) {
			frappe.query_reports["General Ledger"].onload(report);
		}
		
		report.page.add_inner_button(__("Download Colored Excel"), function() {
			let filters = report.get_values();
			let url = frappe.urllib.get_full_url("/api/method/report_center.report_center.report.general_ledger_audit.general_ledger_audit.download_colored_excel");
			open_url_post(url, { filters: JSON.stringify(filters) });
		});
	},

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// If posting_date and creation date differ, wrap cell value to display as red text
		if (data && data.posting_date && data.creation) {
			const posting_date = data.posting_date; // string: YYYY-MM-DD
			const creation_date = data.creation.split(' ')[0]; // string: YYYY-MM-DD (extract from datetime)

			if (posting_date !== creation_date) {
				value = `<span style="color: #d9534f; font-weight: bold;">${value}</span>`;
			}
		}

		return value;
	},

	after_datatable_render: function(datatable) {
		// Highlight entire rows in red background where posting_date != creation.date()
		const visibleRows = datatable.datamanager.getRows();
		visibleRows.forEach(row => {
			const rowIndex = row.meta.rowIndex;
			const raw_data = datatable.options.data[rowIndex];

			if (raw_data && raw_data.posting_date && raw_data.creation) {
				const posting_date = raw_data.posting_date;
				const creation_date = raw_data.creation.split(' ')[0];

				if (posting_date !== creation_date) {
					const rowEl = datatable.rowmanager.getRow$(rowIndex);
					if (rowEl) {
						// Apply soft red background to the row element
						rowEl.style.backgroundColor = "#fff1f1";
						rowEl.style.setProperty("background-color", "#fff1f1", "important");

						// Apply soft red background and red text color to all cells in the row
						rowEl.querySelectorAll('.dt-cell').forEach(cell => {
							cell.style.backgroundColor = "#fff1f1";
							cell.style.setProperty("background-color", "#fff1f1", "important");
							cell.style.color = "#d9534f";
						});
					}
				}
			}
		});
	}
};
