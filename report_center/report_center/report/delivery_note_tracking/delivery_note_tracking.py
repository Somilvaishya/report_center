# Copyright (c) 2026, Report Center and contributors
# For license information, please see license.txt

"""Delivery Note Tracking, in two views.

Tree: one tree per Delivery Note. The DN is the root row and carries everything
that belongs to the whole document (party, locations, GSTINs, status, grand
total, transport and, when one invoice bills it, that invoice's IRN and e-way
bill). Its items sit underneath with what was invoiced against them. An item
billed across more than one invoice gets one more level: a row per invoice.

Normal: one flat row per DN item and invoice, the DN's details repeated on every
row. This is also what an export of the tree view writes, so a spreadsheet always
gets complete rows (see the .js).

Amounts: a tree root shows grand totals (tax included). Every item or invoice
line, in both views, shows the line's taxable value, the "Amount" on the
document's item table. When an invoice also bills other DNs, the root shows only
this DN's share of the invoice's grand total, in proportion to the taxable value
of its lines. In the normal view an item's DN Qty and DN Value sit on its first
row only, so a column total never counts an item twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

PENDING = "Pending"
TREE, NORMAL = "Tree", "Normal"
CHUNK = 500


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data, totals = get_data(filters)
	for row in data:
		row["currency"] = currency
	return get_columns(), data, None, None, get_summary(totals, currency)


def get_columns():
	def col(fieldname, label, fieldtype="Data", width=120, options=None):
		c = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("delivery_note", "Delivery Note No", "Link", 190, "Delivery Note"),
		col("posting_date", "Posting Date", "Date", 100),
		col("customer", "Customer Code", "Link", 120, "Customer"),
		col("customer_name", "Customer Name", "Data", 180),
		col("location_from", "Billing Location-From", "Link", 150, "Location"),
		col("location_to", "Billing Location-To", "Link", 150, "Location"),
		col("destination", "Destination", "Data", 110),
		col("item_code", "Item Code", "Link", 120, "Item"),
		col("item_name", "Item Name", "Data", 180),
		col("item_group", "Item Group", "Link", 120, "Item Group"),
		col("gst_hsn_code", "HSN Code", "Data", 90),
		col("qty", "DN Qty", "Float", 90),
		col("dn_status", "DN Status", "Data", 110),
		col("dn_value", "DN Value", "Currency", 120, "currency"),
		col("billing_address_gstin", "Billing Address GSTIN", "Data", 150),
		col("company_gstin", "Company GSTIN", "Data", 150),
		col("sales_invoice", "Sales Invoice", "Link", 160, "Sales Invoice"),
		col("invoice_date", "Invoice Date", "Date", 100),
		col("invoice_time", "Invoice Time", "Time", 90),
		col("place_of_supply", "Place of Supply", "Data", 140),
		col("invoice_qty", "Invoice Item Qty", "Float", 100),
		col("invoice_value", "Invoice Value", "Currency", 120, "currency"),
		col("irn", "IRN", "Data", 150),
		col("ack_no", "Ack No", "Data", 130),
		col("ack_date", "Acknowledged On", "Datetime", 150),
		col("ewaybill", "E-Way No", "Data", 120),
		col("ewaybill_date", "E-Way Date", "Datetime", 150),
		col("transporter_name", "Transporter Name", "Data", 160),
		col("transporter_gstin", "Transporter GSTIN", "Data", 150),
		col("vehicle_type", "VH Type", "Data", 90),
		col("vehicle_no", "VH No", "Data", 110),
	]


# ---------------------------------------------------------------- fetching


def present(doctype, fields):
	"""Fields that exist on this site; india_compliance and branch apps are optional."""
	meta = frappe.get_meta(doctype)
	standard = (*frappe.model.default_fields, *frappe.model.child_table_fields)
	return [f for f in fields if f in standard or meta.has_field(f)]


def chunks(names):
	names = list(names)
	for i in range(0, len(names), CHUNK):
		yield names[i : i + CHUNK]


def get_data(filters):
	dns = get_delivery_notes(filters)
	if not dns:
		return [], []
	items = get_items(dns, filters.item_code)
	lines = get_invoice_lines(dns)
	invoices = get_invoices({l.sales_invoice for l in lines}, filters.company)
	lines = [l for l in lines if l.sales_invoice in invoices]  # drop invoices the user can't see
	return build_rows(dns, items, lines, invoices, filters.view or TREE)


def get_delivery_notes(filters):
	conditions = [["company", "=", filters.company], ["docstatus", "=", 1]]
	if filters.from_date:
		conditions.append(["posting_date", ">=", filters.from_date])
	if filters.to_date:
		conditions.append(["posting_date", "<=", filters.to_date])
	for key, field in (("customer", "customer"), ("delivery_note", "name"), ("dn_status", "status")):
		if filters.get(key):
			conditions.append([field, "=", filters.get(key)])
	if filters.location and frappe.get_meta("Delivery Note").has_field("location"):
		conditions.append(["location", "=", filters.location])
	if filters.item_code:
		conditions.append(["Delivery Note Item", "item_code", "=", filters.item_code])

	fields = present(
		"Delivery Note",
		[
			"name", "posting_date", "customer", "customer_name", "location", "billing_location",
			"custom_destination", "status", "base_grand_total", "base_net_total", "billing_address_gstin",
			"company_gstin", "ewaybill", "transporter_name", "gst_transporter_id", "gst_vehicle_type", "vehicle_no",
		],
	)
	dns = frappe.get_list(
		"Delivery Note", filters=conditions, fields=fields, order_by="posting_date desc, name desc", distinct=True
	)
	return {d.name: d for d in dns}


def get_items(dns, item_code=None):
	fields = present(
		"Delivery Note Item",
		["name", "parent", "idx", "item_code", "item_name", "item_group", "gst_hsn_code", "qty", "base_net_amount"],
	)
	select = ", ".join(f"`{f}`" for f in fields)
	extra = " and item_code = %(item_code)s" if item_code else ""
	items = []
	for part in chunks(dns):
		items += frappe.db.sql(
			f"""select {select} from `tabDelivery Note Item`
			where parent in %(names)s and parenttype = 'Delivery Note'{extra}
			order by parent, idx""",
			{"names": part, "item_code": item_code},
			as_dict=True,
		)
	return items


def get_invoice_lines(dns):
	"""Invoiced qty and taxable value per (DN item, invoice). Credit notes come in negative."""
	lines = []
	for part in chunks(dns):
		lines += frappe.db.sql(
			"""select delivery_note, dn_detail, parent as sales_invoice, sum(qty) as qty, sum(base_net_amount) as net
			from `tabSales Invoice Item`
			where docstatus = 1 and delivery_note in %(names)s and ifnull(dn_detail, '') != ''
			group by delivery_note, dn_detail, parent""",
			{"names": part},
			as_dict=True,
		)
	return lines


def get_invoices(names, company):
	if not names:
		return {}
	fields = present(
		"Sales Invoice",
		[
			"name", "posting_date", "posting_time", "place_of_supply", "base_grand_total", "base_net_total",
			"irn", "ewaybill", "transporter_name", "gst_transporter_id", "gst_vehicle_type", "vehicle_no",
			"custom_destination",
		],
	)
	invoices = {}
	for part in chunks(names):
		for si in frappe.get_list(
			"Sales Invoice", filters={"name": ["in", part], "company": company, "docstatus": 1}, fields=fields
		):
			invoices[si.name] = si

	acks = log_values("e-Invoice Log", "irn", ["acknowledgement_number", "acknowledged_on"], invoices, "irn")
	ewbs = log_values("e-Waybill Log", "e_waybill_number", ["created_on"], invoices, "ewaybill")
	for si in invoices.values():
		ack = acks.get(si.get("irn")) or {}
		si.ack_no, si.ack_date = ack.get("acknowledgement_number"), ack.get("acknowledged_on")
		si.ewaybill_date = (ewbs.get(si.get("ewaybill")) or {}).get("created_on")
	return invoices


def log_values(doctype, key, fields, invoices, source):
	"""Ack details from e-Invoice Log by IRN, e-way bill date from e-Waybill Log, when india_compliance is in."""
	keys = {si.get(source) for si in invoices.values() if si.get(source)}
	if not keys or not frappe.db.table_exists(doctype):
		return {}
	out = {}
	for part in chunks(keys):
		for row in frappe.get_all(doctype, filters={key: ["in", part]}, fields=[key, *fields]):
			out[row[key]] = row
	return out


# ---------------------------------------------------------------- building


def invoice_share(si, net):
	"""This DN's part of an invoice's grand total, by the taxable value of its lines."""
	if not flt(si.base_net_total):
		return flt(si.base_grand_total) if net else 0.0
	return flt(si.base_grand_total) * flt(net) / flt(si.base_net_total)


def as_time(value):
	"""HH:MM:SS text; the database hands back a timedelta, which a spreadsheet can't show as a time."""
	if value is None or isinstance(value, str):
		return value
	seconds = int(value.total_seconds())
	return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def invoice_fields(si):
	return {
		"sales_invoice": si.name,
		"invoice_date": si.posting_date,
		"invoice_time": as_time(si.get("posting_time")),
		"place_of_supply": si.get("place_of_supply"),
		"irn": si.get("irn"),
		"ack_no": si.get("ack_no"),
		"ack_date": si.get("ack_date"),
		"ewaybill": si.get("ewaybill"),
		"ewaybill_date": si.get("ewaybill_date"),
		"transporter_name": si.get("transporter_name"),
		"transporter_gstin": si.get("gst_transporter_id"),
		"vehicle_type": si.get("gst_vehicle_type"),
		"vehicle_no": si.get("vehicle_no"),
	}


def with_invoice(row, si):
	"""The invoice's details on a row; its transport replaces the DN's only where it has one."""
	for key, value in invoice_fields(si).items():
		if value or key not in row:
			row[key] = value
	if not row.get("destination"):
		row["destination"] = si.get("custom_destination")
	return row


def invoice_label(count):
	return PENDING if not count else _("{0} Invoices").format(count)


def dn_fields(dn):
	"""What belongs to the whole DN: on the tree's root row, repeated on every normal row."""
	return {
		"delivery_note": dn.name,
		"posting_date": dn.posting_date,
		"customer": dn.customer,
		"customer_name": dn.customer_name,
		"location_from": dn.get("location"),
		"location_to": dn.get("billing_location"),
		"destination": dn.get("custom_destination"),
		"dn_status": dn.status,
		"billing_address_gstin": dn.get("billing_address_gstin"),
		"company_gstin": dn.get("company_gstin"),
		"ewaybill": dn.get("ewaybill"),
		"transporter_name": dn.get("transporter_name"),
		"transporter_gstin": dn.get("gst_transporter_id"),
		"vehicle_type": dn.get("gst_vehicle_type"),
		"vehicle_no": dn.get("vehicle_no"),
	}


def item_fields(it):
	return {
		"item_code": it.item_code,
		"item_name": it.item_name,
		"item_group": it.get("item_group"),
		"gst_hsn_code": it.get("gst_hsn_code"),
	}


def build_rows(dns, items, lines, invoices, view=TREE):
	"""Rows for the chosen view, plus one totals row per DN for the summary (the same in both views)."""
	items_of, lines_of, billed_of = {}, {}, {}
	for it in items:
		items_of.setdefault(it.parent, []).append(it)
	for l in lines:
		lines_of.setdefault(l.dn_detail, []).append(l)
		billed = billed_of.setdefault(l.delivery_note, {})
		billed[l.sales_invoice] = billed.get(l.sales_invoice, 0) + flt(l.net)

	def by_date(name):
		return (invoices[name].posting_date, name)

	data, totals = [], []
	for dn in dns.values():
		dn_items = items_of.get(dn.name)
		if not dn_items:  # item filter left nothing of this DN
			continue
		billed = billed_of.get(dn.name, {})
		names = sorted(billed, key=by_date)
		lines_by_item = {
			it.name: sorted(lines_of.get(it.name, []), key=lambda l: by_date(l.sales_invoice)) for it in dn_items
		}
		total = {
			"qty": sum(flt(i.qty) for i in dn_items),
			"dn_value": flt(dn.base_grand_total),
			"invoice_qty": sum(flt(l.qty) for its in lines_by_item.values() for l in its),
			"invoice_value": sum(invoice_share(invoices[n], billed[n]) for n in names),
			"invoiced": bool(names),
		}
		totals.append(total)

		if view == NORMAL:
			data += normal_rows(dn, dn_items, lines_by_item, invoices)
		else:
			data += tree_rows(dn, dn_items, lines_by_item, invoices, names, total)
	return data, totals


def tree_rows(dn, dn_items, lines_by_item, invoices, names, total):
	single = invoices[names[0]] if len(names) == 1 else None
	root = {
		**dn_fields(dn),
		"parent_delivery_note": None,
		"indent": 0,
		"qty": total["qty"],
		"dn_value": total["dn_value"],
		"sales_invoice": invoice_label(len(names)),
		"invoice_qty": total["invoice_qty"],
		"invoice_value": total["invoice_value"],
	}
	if single:
		with_invoice(root, single)
	rows = [root]

	for it in dn_items:
		its = lines_by_item[it.name]
		row = {
			"parent_delivery_note": dn.name,
			"indent": 1,
			**item_fields(it),
			"qty": flt(it.qty),
			"dn_value": flt(it.base_net_amount),
			"invoice_qty": sum(flt(l.qty) for l in its),
			"invoice_value": sum(flt(l.net) for l in its),
		}
		if not its:
			row["sales_invoice"] = PENDING
		elif len(its) > 1:
			row["sales_invoice"] = invoice_label(len(its))
		elif not single:  # the root can't hold this item's invoice, so the item does
			row.update(invoice_fields(invoices[its[0].sales_invoice]))
		rows.append(row)

		if len(its) > 1:
			for l in its:
				rows.append(
					{
						"parent_delivery_note": dn.name,
						"indent": 2,
						**invoice_fields(invoices[l.sales_invoice]),
						"invoice_qty": flt(l.qty),
						"invoice_value": flt(l.net),
					}
				)
	return rows


def normal_rows(dn, dn_items, lines_by_item, invoices):
	head = dn_fields(dn)
	rows = []
	for it in dn_items:
		for i, l in enumerate(lines_by_item[it.name] or [None]):
			row = {
				**head,
				**item_fields(it),
				# the item's own qty and value on its first row only, so totals don't double
				"qty": flt(it.qty) if i == 0 else None,
				"dn_value": flt(it.base_net_amount) if i == 0 else None,
			}
			if l:
				with_invoice(row, invoices[l.sales_invoice])
				row.update(invoice_qty=flt(l.qty), invoice_value=flt(l.net))
			else:
				row.update(sales_invoice=PENDING, invoice_qty=0.0, invoice_value=0.0)
			rows.append(row)
	return rows


def get_summary(totals, currency):
	total = lambda f: sum(flt(t[f]) for t in totals)  # noqa: E731
	pending = sum(1 for t in totals if not t["invoiced"])
	return [
		{"label": _("Delivery Notes"), "value": len(totals), "datatype": "Int"},
		{"label": _("DN Value (with tax)"), "value": total("dn_value"), "datatype": "Currency", "currency": currency},
		{"label": _("Invoice Value (with tax)"), "value": total("invoice_value"), "datatype": "Currency", "currency": currency},
		{"label": _("DN Qty"), "value": total("qty"), "datatype": "Float"},
		{"label": _("Invoiced Qty"), "value": total("invoice_qty"), "datatype": "Float"},
		{"label": _("DNs not invoiced"), "value": pending, "datatype": "Int", "indicator": "Orange" if pending else "Green"},
	]


@frappe.whitelist()
def get_dn_statuses():
	"""Statuses actually in use, since apps add some (e.g. BNS Internally Transferred) that aren't in the DocType."""
	frappe.has_permission("Delivery Note", throw=True)
	return frappe.get_all("Delivery Note", filters={"docstatus": 1}, pluck="status", distinct=True, order_by="status")
