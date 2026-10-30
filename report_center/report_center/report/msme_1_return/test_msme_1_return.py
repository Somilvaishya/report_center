import io
import zipfile
from unittest.mock import patch

import frappe
import openpyxl
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from report_center.report_center.report.msme_1_return import msme_1_return as m


def entry(voucher_no, date, net, kind, voucher_type=None, treds=False):
	"""A ledger line as get_ledger hands it to fifo: net > 0 is a bill, net < 0 settles."""
	date = getdate(date)
	return frappe._dict(
		voucher_no=voucher_no,
		voucher_type=voucher_type or ("Purchase Invoice" if net > 0 else "Payment Entry"),
		date=date,
		bill_date=date,
		net=net,
		kind=kind,
		treds=treds,
		bill_no=None,
	)


def summarise(entries, from_date="2025-10-01", to_date="2026-03-31"):
	report = m.MSMEReturn(frappe._dict(from_date=from_date, to_date=to_date, reason="."))
	info = frappe._dict(name="SUP-1", supplier_name="Test Supplier", pan="abcde1234f", custom_msme_type="Micro")
	return report.summarise(info, m.fifo(entries))


class TestMSME1Return(FrappeTestCase):
	def test_unallocated_payment_settles_oldest_invoice_first(self):
		bills = m.fifo(
			[
				entry("PI-NEW", "2025-11-01", 500, "invoice"),
				entry("PI-OLD", "2025-10-01", 300, "invoice"),
				entry("PE-1", "2025-11-10", -400, "payment"),
			]
		)
		by_name = {b.voucher_no: b for b in bills}
		self.assertEqual([(a.voucher_no, a.amount) for a in by_name["PI-OLD"].allocations], [("PE-1", 300)])
		self.assertEqual([(a.voucher_no, a.amount) for a in by_name["PI-NEW"].allocations], [("PE-1", 100)])
		self.assertEqual(by_name["PI-NEW"].open_on(getdate("2025-11-30")), 400)

	def test_advance_settles_later_invoice_on_its_own_date(self):
		bills = m.fifo([entry("PE-ADV", "2025-10-05", -1000, "payment"), entry("PI-1", "2025-12-20", 600, "invoice")])
		(allocation,) = bills[0].allocations
		self.assertEqual((allocation.voucher_no, allocation.amount, allocation.date), ("PE-ADV", 600, getdate("2025-12-20")))

	def test_return_columns(self):
		row = summarise(
			[
				entry("PI-D", "2025-09-20", 40, "invoice"),  # oldest, so the TReDS payment lands here
				entry("PE-T", "2025-10-02", -40, "payment", treds=True),
				entry("PI-A", "2025-10-01", 100, "invoice"),  # paid on day 30: within 45
				entry("PE-A", "2025-10-31", -100, "payment"),
				entry("PI-B", "2025-10-01", 200, "invoice"),  # paid on day 61: after 45
				entry("PE-B", "2025-12-01", -150, "payment"),  # 50 still open at 31-03: > 45 days
				entry("PI-C", "2026-03-10", 70, "invoice"),  # open at 31-03, 21 days old
			]
		)
		self.assertEqual((row["tr_no"], row["tr_amt"]), (1, 40))
		self.assertEqual((row["other_no"], row["other_amt"]), (1, 100))
		self.assertEqual((row["late_no"], row["late_amt"]), (1, 150))
		self.assertEqual((row["out_le_no"], row["out_le_amt"]), (1, 70))
		self.assertEqual((row["out_gt_no"], row["out_gt_amt"]), (1, 50))
		self.assertEqual(row["pan"], "ABCDE1234F")

	def test_day_45_is_on_time_and_day_46_is_late(self):
		row = summarise(
			[
				entry("PI-45", "2025-10-01", 100, "invoice"),
				entry("PE-45", "2025-11-15", -100, "payment"),  # 45 days later
				entry("PI-46", "2025-10-02", 100, "invoice"),
				entry("PE-46", "2025-11-17", -100, "payment"),  # 46 days later
			]
		)
		self.assertEqual((row["other_no"], row["other_amt"], row["late_no"], row["late_amt"]), (1, 100, 1, 100))

	def test_rounding_paise_do_not_count_an_invoice(self):
		row = summarise(
			[
				entry("PI-1", "2025-08-01", 100.2, "invoice"),
				entry("PE-1", "2025-09-01", -100, "payment"),  # before the period
				entry("JV-ROUND", "2025-11-01", -0.2, "payment", voucher_type="Journal Entry"),
			]
		)
		self.assertEqual((row["late_no"], row["late_amt"], row["out_gt_no"]), (0, 0, 0))

	def test_payment_before_the_period_is_not_reported(self):
		row = summarise([entry("PI-1", "2025-08-01", 100, "invoice"), entry("PE-1", "2025-09-01", -100, "payment")])
		self.assertEqual(row["other_amt"] + row["late_amt"] + row["out_le_amt"] + row["out_gt_amt"], 0)

	def test_debit_note_reduces_invoice_but_is_not_a_payment(self):
		row = summarise(
			[
				entry("PI-1", "2025-10-01", 100, "invoice"),
				entry("PI-RET", "2025-10-05", -30, "adjustment", voucher_type="Purchase Invoice"),
				entry("PE-1", "2025-10-20", -70, "payment"),
			]
		)
		self.assertEqual((row["other_no"], row["other_amt"], row["out_le_amt"], row["out_gt_amt"]), (1, 70, 0, 0))

	def test_set_off_takes_back_the_latest_payment(self):
		row = summarise(
			[
				entry("PI-OLD", "2025-08-01", 100, "invoice"),
				entry("PE-OLD", "2025-08-10", -100, "payment"),
				entry("PI-NEW", "2025-10-05", 200, "invoice"),
				entry("PE-NEW", "2025-10-20", -200, "payment"),
				entry("JV-SETOFF", "2026-03-31", 150, "refund", voucher_type="Journal Entry"),
			]
		)
		# 150 of PE-NEW went to the customer side: PI-NEW is only 50 paid and 150 overdue (177 days old).
		self.assertEqual((row["other_no"], row["other_amt"]), (1, 50))
		self.assertEqual((row["out_gt_no"], row["out_gt_amt"], row["out_le_amt"]), (1, 150, 0))

	def test_refund_cancels_an_unused_advance_before_reopening_invoices(self):
		row = summarise(
			[
				entry("PI-1", "2025-10-01", 100, "invoice"),
				entry("PE-1", "2025-10-10", -160, "payment"),  # 60 left over as advance
				entry("PE-REFUND", "2025-11-01", 80, "refund"),  # 60 of advance, then 20 of PI-1's payment
			]
		)
		self.assertEqual((row["other_amt"], row["out_gt_amt"]), (80, 20))

	def test_set_off_credit_is_not_an_invoice(self):
		row = summarise(
			[
				entry("PE-1", "2026-02-01", -500, "payment"),
				entry("JV-SETOFF", "2026-03-31", 500, "refund", voucher_type="Journal Entry"),
			]
		)
		self.assertEqual(row["out_le_no"] + row["other_no"], 0)

	def msme_suppliers(self, suppliers, details, legacy=True, msme_type=None):
		"""Run get_suppliers over fake Supplier rows and MSME Details rows."""
		report = m.MSMEReturn(frappe._dict(from_date="2026-04-01", to_date="2026-09-30", msme_type=msme_type))

		def get_all(doctype, **kwargs):
			rows = suppliers if doctype == "Supplier" else details
			return [frappe._dict(r) for r in rows]

		with (
			patch.object(m.frappe, "get_all", side_effect=get_all),
			patch.object(m.frappe.db, "has_column", return_value=legacy),
			patch.object(m.frappe.db, "table_exists", return_value=True),
		):
			return {name: s.custom_msme_type for name, s in report.get_suppliers().items()}

	def test_msme_details_table_decides_over_the_old_fields(self):
		suppliers = [
			{"name": "S-NEW", "custom_msme_registered": "No", "custom_msme_type": None},
			{"name": "S-MEDIUM", "custom_msme_registered": "Yes", "custom_msme_type": "Micro"},
			{"name": "S-OLD", "custom_msme_registered": "Yes", "custom_msme_type": "Micro"},
		]
		details = [
			{"parent": "S-NEW", "msme_registered": "Yes", "msme_type": "Small", "effective_from": "2026-04-01"},
			{"parent": "S-MEDIUM", "msme_registered": "Yes", "msme_type": "Medium", "effective_from": "2026-04-01"},
		]
		self.assertEqual(self.msme_suppliers(suppliers, details), {"S-NEW": "Small", "S-OLD": "Micro"})

	def test_latest_msme_row_in_force_at_period_end_wins(self):
		suppliers = [{"name": "S-1"}, {"name": "S-LATER"}]
		details = [  # oldest first, as get_msme_details orders them
			{"parent": "S-1", "msme_registered": "Yes", "msme_type": "Micro", "effective_from": None},
			{"parent": "S-1", "msme_registered": "Yes", "msme_type": "Small", "effective_from": "2026-06-01"},
			{"parent": "S-1", "msme_registered": "No", "msme_type": None, "effective_from": "2026-10-01"},
			{"parent": "S-LATER", "msme_registered": "Yes", "msme_type": "Micro", "effective_from": "2026-10-01"},
		]
		self.assertEqual(self.msme_suppliers(suppliers, details, legacy=False), {"S-1": "Small"})

	def test_old_fields_ignored_where_the_site_no_longer_has_them(self):
		self.assertEqual(self.msme_suppliers([{"name": "S-1"}], [], legacy=False), {})

	def test_msme_type_filter_applies_to_the_table(self):
		suppliers = [{"name": "S-MICRO"}, {"name": "S-SMALL"}]
		details = [
			{"parent": "S-MICRO", "msme_registered": "Yes", "msme_type": "Micro", "effective_from": "2026-04-01"},
			{"parent": "S-SMALL", "msme_registered": "Yes", "msme_type": "Small", "effective_from": "2026-04-01"},
		]
		self.assertEqual(self.msme_suppliers(suppliers, details, legacy=False, msme_type="Small"), {"S-SMALL": "Small"})

	def test_template_fill_changes_only_the_data_rows(self):
		with open(m.TEMPLATE, "rb") as f:
			template = f.read()
		rows = [
			{"sno": 1, "supplier_name": "A & B Traders", "pan": "ABCDE1234F", "other_no": 2, "other_amt": 1500.5, "reason": "."},
			{"sno": 2, "supplier_name": "C Co", "pan": "FGHIJ5678K", "late_no": 1, "late_amt": 200, "reason": "."},
		]
		for row in rows:
			for f in m.AMOUNT_COLS + m.COUNT_COLS:
				row.setdefault(f, 0)
		out = m.fill_template(template, rows)

		before, after = zipfile.ZipFile(io.BytesIO(template)), zipfile.ZipFile(io.BytesIO(out))
		self.assertEqual([i.filename for i in before.infolist()], [i.filename for i in after.infolist()])
		changed = [i.filename for i in before.infolist() if before.read(i.filename) != after.read(i.filename)]
		self.assertEqual(changed, [m.SHEET])

		sheet = openpyxl.load_workbook(io.BytesIO(out))["MSME"]
		self.assertEqual(
			[c.value for c in sheet[4]], [1, "A & B Traders", "ABCDE1234F", 0, 0, 2, 1500.5, 0, 0, 0, 0, 0, 0, "."]
		)
		self.assertEqual(sheet["I5"].value, 200)
		self.assertIsNone(sheet["A6"].value)
		self.assertTrue(sheet.protection.sheet)
		self.assertIn('<c r="G100003"', after.read(m.SHEET).decode())
		self.assertRegex(after.read(m.SHEET).decode(), r'<c r="G100003"[^>]*>.*?</f><v>1501</v>')
