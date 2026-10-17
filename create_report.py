import frappe

def create():
    reports = [
        {"name": "Sales Movement Summary", "ref_doctype": "Sales Order"},
        {"name": "Batch Traceability", "ref_doctype": "Batch"},
        {"name": "Manufacturing and Packaging Journey", "ref_doctype": "Stock Entry"},
    ]
    for r in reports:
        report_name = r["name"]
        if frappe.db.exists("Report", report_name):
            print(f"Report '{report_name}' already exists.")
            continue

        doc = frappe.get_doc({
            "doctype": "Report",
            "report_name": report_name,
            "ref_doctype": r["ref_doctype"],
            "report_type": "Script Report",
            "is_standard": "Yes",
            "module": "Report Center"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Report '{report_name}' created successfully.")
