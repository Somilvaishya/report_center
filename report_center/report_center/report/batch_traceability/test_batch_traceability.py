from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from report_center.report_center.report.batch_traceability.batch_traceability import execute


class TestBatchTraceability(FrappeTestCase):
	"""Builds PR -> transfer -> manufacture -> DN + SI on the site's own masters; rolled back afterwards."""

	def setUp(self):
		# Other apps' doc_events (location series, GST checks...) need site setup that has nothing to do
		# with tracing; ERPNext's own controllers, which create the batch bundles, still run.
		with patch("frappe.get_doc_hooks", return_value={}):
			self.make_chain()

	def make_chain(self):
		self.company = get_company()
		self.store, self.wip = frappe.get_all(
			"Warehouse",
			filters={"company": self.company, "is_group": 0, "disabled": 0},
			pluck="name",
			order_by="name",
			limit=2,
		)
		self.supplier = frappe.get_all("Supplier", filters={"disabled": 0}, pluck="name", limit=1)[0]
		self.customer = frappe.get_all("Customer", filters={"disabled": 0}, pluck="name", limit=1)[0]

		suffix = frappe.generate_hash(length=6).upper()
		self.rm = make_item(f"_Test BT RM {suffix}")
		self.fg = make_item(f"_Test BT FG {suffix}")
		self.rm_batch = make_batch(self.rm, f"BT-RM-{suffix}")
		self.fg_batch = make_batch(self.fg, f"BT-FG-{suffix}")

		self.pr = self.submit(
			"Purchase Receipt",
			supplier=self.supplier,
			items=[self.line(self.rm, 10, self.rm_batch, warehouse=self.store, rate=100)],
		)
		self.transfer = self.submit(
			"Stock Entry",
			purpose="Material Transfer",
			stock_entry_type="Material Transfer",
			items=[self.line(self.rm, 10, self.rm_batch, s_warehouse=self.store, t_warehouse=self.wip)],
		)
		bom = self.submit("BOM", item=self.fg, quantity=1, items=[{"item_code": self.rm, "qty": 2, "rate": 100}])
		self.manufacture = self.submit(
			"Stock Entry",
			purpose="Manufacture",
			stock_entry_type="Manufacture",
			from_bom=1,
			bom_no=bom.name,
			fg_completed_qty=4,
			items=[
				self.line(self.rm, 8, self.rm_batch, s_warehouse=self.wip),
				self.line(self.fg, 4, self.fg_batch, t_warehouse=self.store, is_finished_item=1, bom_no=bom.name),
			],
		)
		self.dn = self.submit(
			"Delivery Note",
			customer=self.customer,
			items=[self.line(self.fg, 3, self.fg_batch, warehouse=self.store, rate=500)],
		)
		self.si = self.submit(
			"Sales Invoice",
			customer=self.customer,
			update_stock=1,
			items=[self.line(self.fg, 1, self.fg_batch, warehouse=self.store, rate=500)],
		)

	def line(self, item_code, qty, batch_no, **fields):
		return {"item_code": item_code, "qty": qty, "batch_no": batch_no, "use_serial_batch_fields": 1, **fields}

	def submit(self, doctype, **fields):
		doc = frappe.get_doc({"doctype": doctype, "company": self.company, "posting_date": nowdate(), **fields})
		doc.flags.ignore_mandatory = True  # site-specific custom fields are irrelevant here
		doc.insert()
		doc.submit()
		return doc

	def run_report(self, **filters):
		filters.setdefault("company", self.company)
		return execute(filters)[1]

	def find(self, rows, journey, voucher_no):
		return next(r for r in rows if r["journey"] == journey and r.get("voucher_no") == voucher_no)

	def test_forward_trace_follows_raw_material_to_customer(self):
		rows = self.run_report(batch_no=self.rm_batch, direction="Forward")

		root = rows[0]
		self.assertEqual((root["batch_no"], root["indent"], root["qty"]), (self.rm_batch, 0, 10))
		self.assertEqual(root["balance_qty"], 2)

		received = self.find(rows, "Received from Supplier", self.pr.name)
		self.assertEqual(
			(received["party"], received["to_warehouse"], received["qty"]),
			(self.pr.supplier_name, self.store, 10),
		)

		transfer = self.find(rows, "Transferred", self.transfer.name)
		self.assertEqual(
			(transfer["from_warehouse"], transfer["to_warehouse"], transfer["qty"]), (self.store, self.wip, 10)
		)

		consumed = self.find(rows, "Consumed in Production", self.manufacture.name)
		self.assertEqual((consumed["qty"], consumed["indent"]), (-8, 1))

		# The finished batch hangs under the consumption row, with its own journey below it.
		fg_root = rows[rows.index(consumed) + 1]
		self.assertEqual((fg_root["batch_no"], fg_root["indent"], fg_root["qty"]), (self.fg_batch, 2, 4))

		dispatched = self.find(rows, "Dispatched to Customer", self.dn.name)
		self.assertEqual(
			(dispatched["party"], dispatched["qty"], dispatched["indent"]), (self.dn.customer_name, -3, 3)
		)
		self.assertEqual(self.find(rows, "Dispatched to Customer", self.si.name)["qty"], -1)

	def test_backward_trace_follows_finished_batch_to_supplier(self):
		rows = self.run_report(batch_no=self.fg_batch, direction="Backward")

		self.assertEqual(rows[0]["batch_no"], self.fg_batch)
		produced = self.find(rows, "Produced", self.manufacture.name)
		rm_root = rows[rows.index(produced) + 1]
		self.assertEqual((rm_root["batch_no"], rm_root["indent"]), (self.rm_batch, 2))

		received = self.find(rows, "Received from Supplier", self.pr.name)
		self.assertEqual((received["party"], received["indent"]), (self.pr.supplier_name, 3))

		# Backward does not expand forward again: the finished batch appears once, as the root.
		self.assertEqual(sum(1 for r in rows if r.get("is_batch") and r["batch_no"] == self.fg_batch), 1)

	def test_item_filter_lists_batches_first_seen_in_period(self):
		rows = self.run_report(item_code=self.rm, from_date=nowdate(), to_date=nowdate())
		self.assertEqual([r["batch_no"] for r in rows if r["indent"] == 0], [self.rm_batch])

		rows = self.run_report(item_code=self.rm, from_date="2000-01-01", to_date="2000-01-31")
		self.assertEqual(rows, [])

	def test_all_items_lists_each_batch_once(self):
		today = {"from_date": nowdate(), "to_date": nowdate()}

		# Forward: the finished batch sits under the raw material batch, not again on its own.
		rows = self.run_report(direction="Forward", **today)
		roots = [r["batch_no"] for r in rows if r["indent"] == 0]
		self.assertIn(self.rm_batch, roots)
		self.assertNotIn(self.fg_batch, roots)
		self.assertEqual(sum(1 for r in rows if r.get("is_batch") and r["batch_no"] == self.fg_batch), 1)

		# Backward: the other way round.
		rows = self.run_report(direction="Backward", **today)
		roots = [r["batch_no"] for r in rows if r["indent"] == 0]
		self.assertIn(self.fg_batch, roots)
		self.assertNotIn(self.rm_batch, roots)

	def test_requires_batch_or_period(self):
		self.assertRaises(frappe.ValidationError, execute, {"direction": "Forward"})


def get_company():
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"
	return frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name", limit=1)[0]


def make_item(item_code):
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"has_batch_no": 1,
			"create_new_batch": 0,
		}
	)
	if item.meta.has_field("gst_hsn_code"):  # india_compliance makes it mandatory
		item.gst_hsn_code = frappe.db.get_value("GST HSN Code", {}, "name")
	item.flags.ignore_mandatory = True  # site-specific custom fields are irrelevant here
	return item.insert().name


def make_batch(item_code, batch_id):
	return frappe.get_doc({"doctype": "Batch", "batch_id": batch_id, "item": item_code}).insert().name
