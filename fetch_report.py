import frappe

def execute():
    try:
        report = frappe.get_doc("Report", "CUSTOM PENDING SO ITEM")
        print(f"REPORT QUERY/JSON:\n{report.query}")
        print(f"\nCOLUMNS JSON:\n{report.json}")
    except Exception as e:
        print(f"Error: {e}")
