import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from report_center.report_center.report.delivery_note_tracking import delivery_note_tracking as r


def dn(name, grand, net=None, status="Completed"):
	return frappe._dict(
		name=name, posting_date=getdate("2026-11-01"), customer="C-1", customer_name="ABC Ltd", status=status,
		base_grand_total=grand, base_net_total=grand if net is None else net,
		vehicle_no="DN-VEHICLE", ewaybill=None,
	)


def item(name, parent, qty, net, code="ITEM"):
	return frappe._dict(name=name, parent=parent, item_code=code, item_name=code, qty=qty, base_net_amount=net)


def line(dn_name, dn_detail, si, qty, net):
	return frappe._dict(delivery_note=dn_name, dn_detail=dn_detail, sales_invoice=si, qty=qty, net=net)


def si(name, grand, net=None, date="2026-11-02", **extra):
	return frappe._dict(
		name=name, posting_date=getdate(date), base_grand_total=grand, base_net_total=grand if net is None else net, **extra
	)


def build(dns, items, lines=(), invoices=(), view=r.TREE, with_totals=False):
	data, totals = r.build_rows({d.name: d for d in dns}, list(items), list(lines), {s.name: s for s in invoices}, view)
	return (data, totals) if with_totals else data


def cols(data, *fields):
	return [tuple(row.get(f) for f in fields) for row in data]


class TestDeliveryNoteTracking(FrappeTestCase):
	def test_dn_is_root_and_its_items_sit_under_it(self):
		data = build(
			[dn("DN-1", 118, 100)],
			[item("i1", "DN-1", 6, 60, "A"), item("i2", "DN-1", 4, 40, "B")],
			[line("DN-1", "i1", "SI-1", 6, 60), line("DN-1", "i2", "SI-1", 4, 40)],
			[si("SI-1", 118, 100, irn="IRN-1", ack_no="ACK-1", vehicle_no="SI-VEHICLE")],
		)
		self.assertEqual(
			cols(data, "indent", "delivery_note", "item_code", "qty", "dn_value", "sales_invoice", "invoice_qty", "invoice_value"),
			[(0, "DN-1", None, 10, 118, "SI-1", 10, 118), (1, None, "A", 6, 60, None, 6, 60), (1, None, "B", 4, 40, None, 4, 40)],
		)
		# one invoice: its IRN and transport sit on the DN row and override the DN's own
		self.assertEqual(cols(data[:1], "irn", "ack_no", "vehicle_no"), [("IRN-1", "ACK-1", "SI-VEHICLE")])
		self.assertEqual({row["parent_delivery_note"] for row in data[1:]}, {"DN-1"})

	def test_unbilled_dn_is_pending_and_keeps_its_own_transport(self):
		data = build([dn("DN-1", 50)], [item("i1", "DN-1", 5, 50)])
		self.assertEqual(cols(data, "sales_invoice", "invoice_value", "vehicle_no"), [("Pending", 0, "DN-VEHICLE"), ("Pending", 0, None)])

	def test_items_billed_in_different_invoices_carry_their_own(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 6, 60, "A"), item("i2", "DN-1", 4, 40, "B")],
			[line("DN-1", "i1", "SI-1", 6, 60), line("DN-1", "i2", "SI-2", 4, 40)],
			[si("SI-1", 60, irn="IRN-1"), si("SI-2", 40, date="2026-11-03", irn="IRN-2")],
		)
		self.assertEqual(
			cols(data, "indent", "sales_invoice", "irn", "invoice_value"),
			[(0, "2 Invoices", None, 100), (1, "SI-1", "IRN-1", 60), (1, "SI-2", "IRN-2", 40)],
		)

	def test_item_split_across_invoices_gets_a_row_per_invoice(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 10, 100)],
			[line("DN-1", "i1", "SI-2", 7, 70), line("DN-1", "i1", "SI-1", 3, 30)],
			[si("SI-1", 30), si("SI-2", 70, date="2026-11-05")],
		)
		self.assertEqual(
			cols(data, "indent", "sales_invoice", "invoice_qty", "invoice_value"),
			[(0, "2 Invoices", 10, 100), (1, "2 Invoices", 10, 100), (2, "SI-1", 3, 30), (2, "SI-2", 7, 70)],
		)

	def test_invoice_covering_two_dns_is_shared_by_taxable_value(self):
		# SI-1: 118 grand on 100 taxable; DN-1's 60 of it carries 70.8, DN-2's 40 carries 47.2
		data = build(
			[dn("DN-1", 70.8, 60), dn("DN-2", 47.2, 40)],
			[item("a", "DN-1", 6, 60), item("b", "DN-2", 4, 40)],
			[line("DN-1", "a", "SI-1", 6, 60), line("DN-2", "b", "SI-1", 4, 40)],
			[si("SI-1", 118, 100)],
		)
		roots = [row for row in data if row["indent"] == 0]
		self.assertEqual(cols(roots, "delivery_note", "invoice_value"), [("DN-1", 70.8), ("DN-2", 47.2)])

	def test_partly_billed_item_and_credit_note(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 10, 100)],
			[line("DN-1", "i1", "SI-1", 10, 100), line("DN-1", "i1", "CN-1", -2, -20)],
			[si("SI-1", 100), si("CN-1", -20, date="2026-11-09")],
		)
		self.assertEqual(cols(data[:2], "invoice_qty", "invoice_value"), [(8, 80), (8, 80)])

	def test_summary_counts_dns_once_in_either_view(self):
		args = (
			[dn("DN-1", 100), dn("DN-2", 50)],
			[item("i1", "DN-1", 10, 100), item("i2", "DN-2", 5, 50)],
			[line("DN-1", "i1", "SI-1", 10, 100)],
			[si("SI-1", 100)],
		)
		for view in (r.TREE, r.NORMAL):
			_data, totals = build(*args, view=view, with_totals=True)
			summary = {s["label"]: s["value"] for s in r.get_summary(totals, "INR")}
			self.assertEqual(
				(summary["Delivery Notes"], summary["DN Value (with tax)"], summary["Invoice Value (with tax)"], summary["DNs not invoiced"]),
				(2, 150, 100, 1),
			)

	def test_normal_view_repeats_the_dn_on_every_row(self):
		data = build(
			[dn("DN-1", 118, 100)],
			[item("i1", "DN-1", 6, 60, "A"), item("i2", "DN-1", 4, 40, "B")],
			[line("DN-1", "i1", "SI-1", 6, 60)],
			[si("SI-1", 70.8, 60, irn="IRN-1", vehicle_no="SI-VEHICLE")],
			view=r.NORMAL,
		)
		self.assertEqual(
			cols(data, "delivery_note", "customer", "item_code", "qty", "dn_value", "sales_invoice", "irn", "invoice_qty", "invoice_value", "vehicle_no"),
			[
				("DN-1", "C-1", "A", 6, 60, "SI-1", "IRN-1", 6, 60, "SI-VEHICLE"),
				("DN-1", "C-1", "B", 4, 40, "Pending", None, 0, 0, "DN-VEHICLE"),
			],
		)
		self.assertFalse(any("indent" in row for row in data))

	def test_normal_view_item_in_two_invoices_counts_its_qty_once(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 10, 100)],
			[line("DN-1", "i1", "SI-2", 7, 70), line("DN-1", "i1", "SI-1", 3, 30)],
			[si("SI-1", 30), si("SI-2", 70, date="2026-11-05")],
			view=r.NORMAL,
		)
		self.assertEqual(
			cols(data, "delivery_note", "item_code", "qty", "dn_value", "sales_invoice", "invoice_qty", "invoice_value"),
			[("DN-1", "ITEM", 10, 100, "SI-1", 3, 30), ("DN-1", "ITEM", None, None, "SI-2", 7, 70)],
		)
