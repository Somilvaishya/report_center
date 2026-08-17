import frappe
def get_count():
    count = frappe.db.count("Sales Order", {"transaction_date": ["between", ["2026-07-17", "2026-08-17"]]})
    print(f"Total SOs between 2026-07-17 and 2026-08-17: {count}")
    return count
