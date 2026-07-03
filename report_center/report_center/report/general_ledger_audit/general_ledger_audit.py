# Copyright (c) 2026, Antigravity and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from erpnext.accounts.report.general_ledger.general_ledger import execute as execute_gl


def execute(filters=None):
	"""
	General Ledger Audit Report
	Reuses standard General Ledger execution logic and appends 'Created On' (creation) column.
	"""
	# Call the standard ERPNext General Ledger report logic
	columns, data = execute_gl(filters)

	# Locate 'posting_date' to insert 'Created On' column right after it
	insert_index = 2  # default fallback index
	for i, col in enumerate(columns):
		if col.get("fieldname") == "posting_date":
			insert_index = i + 1
			break

	# Insert the 'Created On' column
	columns.insert(insert_index, {
		"label": _("Created On"),
		"fieldname": "creation",
		"fieldtype": "Datetime",
		"width": 150
	})

	return columns, data
