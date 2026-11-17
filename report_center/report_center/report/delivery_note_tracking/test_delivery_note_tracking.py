from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from report_center.report_center.report.delivery_note_tracking import delivery_note_tracking as r


def dn(name, grand, net=None, status="Completed", igst=0, **extra):
	return frappe._dict(
		name=name, posting_date=getdate("2026-11-01"), customer="C-1", customer_name="ABC Ltd", status=status,
		base_grand_total=grand, base_net_total=grand if net is None else net, igst=igst, cgst=0, sgst=0,
		vehicle_no="DN-VEHICLE", ewaybill=None, **extra,
	)


def item(name, parent, qty, net, code="ITEM", igst=0):
	return frappe._dict(name=name, parent=parent, item_code=code, item_name=code, qty=qty, net=net, igst=igst, cgst=0, sgst=0, cess=0)


def line(dn_name, dn_detail, si, qty, net, igst=0):
	return frappe._dict(delivery_note=dn_name, dn_detail=dn_detail, sales_invoice=si, qty=qty, net=net, igst=igst, cgst=0, sgst=0, cess=0)


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
			[dn("DN-1", 118, 100, igst=18)],
			[item("i1", "DN-1", 6, 60, "A", igst=10.8), item("i2", "DN-1", 4, 40, "B", igst=7.2)],
			[line("DN-1", "i1", "SI-1", 6, 60, igst=10.8), line("DN-1", "i2", "SI-1", 4, 40, igst=7.2)],
			[si("SI-1", 118, 100, irn="IRN-1", ack_no="ACK-1", vehicle_no="SI-VEHICLE")],
		)
		self.assertEqual(
			cols(data, "indent", "delivery_note", "item_code", "qty", "dn_net_total", "dn_igst", "dn_grand_total", "sales_invoice", "si_net_total", "si_igst", "si_grand_total"),
			[
				(0, "DN-1", None, 10, 100, 18, 118, "SI-1", 100, 18, 118),
				(1, None, "A", 6, 60, 10.8, 70.8, None, 60, 10.8, 70.8),
				(1, None, "B", 4, 40, 7.2, 47.2, None, 40, 7.2, 47.2),
			],
		)
		# one invoice: its IRN and transport sit on the DN row and override the DN's own
		self.assertEqual(cols(data[:1], "irn", "ack_no", "vehicle_no"), [("IRN-1", "ACK-1", "SI-VEHICLE")])
		self.assertEqual({row["parent_delivery_note"] for row in data[1:]}, {"DN-1"})

	def test_unbilled_dn_is_pending_and_keeps_its_own_transport(self):
		data = build([dn("DN-1", 50)], [item("i1", "DN-1", 5, 50)])
		self.assertEqual(
			cols(data, "sales_invoice", "si_net_total", "si_grand_total", "vehicle_no"),
			[("Pending", 0, 0, "DN-VEHICLE"), ("Pending", 0, 0, None)],
		)

	def test_items_billed_in_different_invoices_carry_their_own(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 6, 60, "A"), item("i2", "DN-1", 4, 40, "B")],
			[line("DN-1", "i1", "SI-1", 6, 60), line("DN-1", "i2", "SI-2", 4, 40)],
			[si("SI-1", 60, irn="IRN-1"), si("SI-2", 40, date="2026-11-03", irn="IRN-2")],
		)
		self.assertEqual(
			cols(data, "indent", "sales_invoice", "irn", "si_grand_total"),
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
			cols(data, "indent", "sales_invoice", "invoice_qty", "si_net_total"),
			[(0, "2 Invoices", 10, 100), (1, "2 Invoices", 10, 100), (2, "SI-1", 3, 30), (2, "SI-2", 7, 70)],
		)

	def test_invoice_covering_two_dns_is_shared_by_taxable_value(self):
		# SI-1: 118 grand on 100 taxable; DN-1's 60 of it carries 70.8, DN-2's 40 carries 47.2
		data = build(
			[dn("DN-1", 70.8, 60), dn("DN-2", 47.2, 40)],
			[item("a", "DN-1", 6, 60), item("b", "DN-2", 4, 40)],
			[line("DN-1", "a", "SI-1", 6, 60, igst=10.8), line("DN-2", "b", "SI-1", 4, 40, igst=7.2)],
			[si("SI-1", 118, 100)],
		)
		roots = [row for row in data if row["indent"] == 0]
		self.assertEqual(
			cols(roots, "delivery_note", "si_net_total", "si_igst", "si_grand_total"),
			[("DN-1", 60, 10.8, 70.8), ("DN-2", 40, 7.2, 47.2)],
		)

	def test_partly_billed_item_and_credit_note(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 10, 100)],
			[line("DN-1", "i1", "SI-1", 10, 100), line("DN-1", "i1", "CN-1", -2, -20)],
			[si("SI-1", 100), si("CN-1", -20, date="2026-11-09")],
		)
		self.assertEqual(cols(data[:2], "invoice_qty", "si_net_total", "si_grand_total"), [(8, 80, 80), (8, 80, 80)])

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
				(summary["Delivery Notes"], summary["DN Grand Total"], summary["SI Grand Total"], summary["DNs not invoiced"]),
				(2, 150, 100, 1),
			)

	def test_normal_view_repeats_the_dn_on_every_row(self):
		data = build(
			[dn("DN-1", 118, 100, return_against="DN-0", return_against_date=getdate("2026-10-01"), location_to="Faridabad, Haryana - 121003")],
			[item("i1", "DN-1", 6, 60, "A", igst=10.8), item("i2", "DN-1", 4, 40, "B", igst=7.2)],
			[line("DN-1", "i1", "SI-1", 6, 60, igst=10.8)],
			[si("SI-1", 70.8, 60, irn="IRN-1", vehicle_no="SI-VEHICLE")],
			view=r.NORMAL,
		)
		self.assertEqual(
			cols(data, "delivery_note", "return_against", "location_to", "item_code", "qty", "dn_grand_total", "sales_invoice", "irn", "si_igst", "si_grand_total", "vehicle_no"),
			[
				("DN-1", "DN-0", "Faridabad, Haryana - 121003", "A", 6, 70.8, "SI-1", "IRN-1", 10.8, 70.8, "SI-VEHICLE"),
				("DN-1", "DN-0", "Faridabad, Haryana - 121003", "B", 4, 47.2, "Pending", None, 0, 0, "DN-VEHICLE"),
			],
		)
		self.assertFalse(any("indent" in row for row in data))

	def test_normal_view_item_in_two_invoices_counts_its_amounts_once(self):
		data = build(
			[dn("DN-1", 100)],
			[item("i1", "DN-1", 10, 100)],
			[line("DN-1", "i1", "SI-2", 7, 70), line("DN-1", "i1", "SI-1", 3, 30)],
			[si("SI-1", 30), si("SI-2", 70, date="2026-11-05")],
			view=r.NORMAL,
		)
		self.assertEqual(
			cols(data, "item_code", "qty", "dn_net_total", "dn_grand_total", "sales_invoice", "invoice_qty", "si_net_total"),
			[("ITEM", 10, 100, 100, "SI-1", 3, 30), ("ITEM", None, None, None, "SI-2", 7, 70)],
		)

	def test_billing_address_is_shortened_to_city_state_pin(self):
		display = (
			"Shed No- B-78, Gurukul Industrial Estate,<br>P O Amarnagar, Faridabad<br>Faridabad<br>\n"
			"Haryana, State Code: 06<br>PIN Code: 121003<br>India<br>\nGSTIN: 06AAJCK9474A1ZF<br>"
		)
		self.assertEqual(r.short_address(display), "Faridabad, Haryana - 121003")
		self.assertIsNone(r.short_address("Some free text address<br>Delhi"))

	def test_return_without_destination_takes_the_original_dns(self):
		dns = {
			"DN-R": frappe._dict(name="DN-R", is_return=1, return_against="DN-0", custom_destination=None),
			"DN-S": frappe._dict(name="DN-S", is_return=1, return_against="DN-0", custom_destination="Agra"),
		}
		original = frappe._dict(name="DN-0", posting_date=getdate("2026-10-01"), custom_destination="Indore")
		frappe.get_meta("Delivery Note")  # load it before get_all is patched; meta loading uses get_all
		with patch.object(frappe, "get_all", return_value=[original]):
			r.add_return_details(dns)
		self.assertEqual(
			[(d.destination, d.return_against_date) for d in dns.values()],
			[("Indore", getdate("2026-10-01")), ("Agra", getdate("2026-10-01"))],
		)
