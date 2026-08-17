import frappe
from report_center.report_center.report_center.report.sales_movement_summary.sales_movement_summary import execute
def run():
    try:
        columns, data = execute({"from_date": "2026-07-17", "to_date": "2026-08-17"})
        print(f"Total Rows returned by execute: {len(data)}")
        if len(data) > 0:
            print(f"First row: {data[0]}")
    except Exception as e:
        print(f"Error: {e}")
