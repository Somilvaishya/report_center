import frappe
def get_count():
    sql = """
        SELECT
            so.name as sales_order,
            dn.name as delivery_note,
            si.name as sales_invoice
        FROM `tabSales Order` so
        LEFT JOIN `tabDelivery Note Item` dni ON dni.against_sales_order = so.name
        LEFT JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
        LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = so.name
        LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        WHERE so.transaction_date BETWEEN '2026-06-01' AND '2026-08-17'
        GROUP BY so.name, dn.name, si.name
    """
    raw_data = frappe.db.sql(sql, as_dict=True)
    print(f"Total Rows returned by Query: {len(raw_data)}")
    return len(raw_data)
