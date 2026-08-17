import frappe
def get_count():
    count = frappe.db.count("Sales Order", {"transaction_date": ["between", ["2026-06-01", "2026-08-17"]]})
    print(f"Total Sales Orders: {count}")
    return count
