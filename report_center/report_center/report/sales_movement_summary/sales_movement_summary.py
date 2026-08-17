import frappe
from frappe.utils import date_diff

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "sales_order", "label": "Sales Order", "fieldtype": "Link", "options": "Sales Order", "width": 130},
        {"fieldname": "customer", "label": "Customer ID", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "width": 180},
        {"fieldname": "so_date", "label": "SO Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "so_status", "label": "SO Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "delivery_note", "label": "Delivery Note", "fieldtype": "Link", "options": "Delivery Note", "width": 130},
        {"fieldname": "dn_date", "label": "DN Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "dn_status", "label": "DN Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "delay_dispatch", "label": "Delay to Dispatch (Days)", "fieldtype": "Int", "width": 170},
        {"fieldname": "delay_status", "label": "Delay Status", "fieldtype": "Data", "width": 120},
        {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
        {"fieldname": "si_date", "label": "SI Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "si_status", "label": "SI Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency", "width": 140},
        {"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Currency", "width": 120},
    ]

def get_data(filters):
    conditions = []
    if filters and filters.get("from_date") and filters.get("to_date"):
        conditions.append(f"so.transaction_date BETWEEN '{filters.get('from_date')}' AND '{filters.get('to_date')}'")
    if filters and filters.get("customer"):
        conditions.append(f"so.customer = '{filters.get('customer')}'")
        
    condition_str = ""
    if conditions:
        condition_str = "WHERE " + " AND ".join(conditions)
    
    # We query Sales Orders and join with Delivery Note Items and Sales Invoice Items
    sql = f"""
        SELECT
            so.name as sales_order,
            so.customer,
            so.customer_name,
            so.transaction_date as so_date,
            so.status as so_status,
            dn.name as delivery_note,
            dn.posting_date as dn_date,
            dn.status as dn_status,
            si.name as sales_invoice,
            si.posting_date as si_date,
            si.status as si_status,
            si.outstanding_amount,
            si.paid_amount
        FROM `tabSales Order` so
        LEFT JOIN `tabDelivery Note Item` dni ON dni.against_sales_order = so.name
        LEFT JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
        LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = so.name
        LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        {condition_str}
        GROUP BY so.name, dn.name, si.name
        ORDER BY so.transaction_date DESC
    """
    
    raw_data = frappe.db.sql(sql, as_dict=True)
    
    data = []
    for row in raw_data:
        delay_dispatch = None
        delay_status = ""
        
        if row.so_date and row.dn_date:
            delay_dispatch = date_diff(row.dn_date, row.so_date)
            if delay_dispatch <= 3:
                delay_status = "On Time"
            elif 3 < delay_dispatch <= 5:
                delay_status = "Warning"
            else:
                delay_status = "Delayed"
                
        row.update({
            "delay_dispatch": delay_dispatch,
            "delay_status": delay_status
        })
        data.append(row)
        
    return data
