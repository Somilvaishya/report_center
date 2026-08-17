import frappe

def create():
    report_name = "Sales Movement Summary"
    if frappe.db.exists("Report", report_name):
        print(f"Report '{report_name}' already exists.")
        return

    doc = frappe.get_doc({
        "doctype": "Report",
        "report_name": report_name,
        "ref_doctype": "Sales Order",
        "report_type": "Script Report",
        "is_standard": "Yes",
        "module": "Report Center"
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Report '{report_name}' created successfully.")
