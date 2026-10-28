"""MSME-1 half-yearly return: payments to Micro and Small suppliers against the 45-day limit.

Payments are matched to invoices first-in-first-out from the supplier's ledger, ignoring how (or
whether) they were allocated in ERPNext. Finance often books a direct Payment Entry without
reconciling it, which leaves invoices showing as outstanding although the supplier has been paid;
FIFO settles the oldest open bill first, the way the supplier's own account would.

A refund, or a set-off that moves the supplier's balance to their customer account, takes money
back: the most recently paid invoices become unpaid again and are aged on their own dates.
"""

import bisect
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

CREDIT_DAYS = 45  # fixed by the form's own column headings
TOLERANCE = 1.0  # a rupee or less left on an invoice is rounding, not an outstanding bill
SUMMARY = "MSME-1 Return"
DETAIL = "Invoice-wise FIFO Detail"

TEMPLATE = os.path.join(os.path.dirname(__file__), "msme_template.xlsx")
SHEET = "xl/worksheets/sheet2.xml"  # the "MSME" sheet in the MCA template
FIRST_ROW, TOTAL_ROW = 4, 100003
COLUMNS = ("tr", "other", "late", "out_le", "out_gt")  # (d)(i), (d)(ii), (e), (f), (g)
AMOUNT_COLS = ("tr_amt", "other_amt", "late_amt", "out_le_amt", "out_gt_amt")
COUNT_COLS = ("tr_no", "other_no", "late_no", "out_le_no", "out_gt_no")
# Column letter, template style and field for each cell of a data row, in form order (a)..(h).
ROW_LAYOUT = (
	("A", 17, "sno"), ("B", 18, "supplier_name"), ("C", 17, "pan"),
	("D", 19, "tr_no"), ("E", 20, "tr_amt"), ("F", 19, "other_no"), ("G", 20, "other_amt"),
	("H", 19, "late_no"), ("I", 20, "late_amt"), ("J", 19, "out_le_no"), ("K", 20, "out_le_amt"),
	("L", 19, "out_gt_no"), ("M", 20, "out_gt_amt"), ("N", 21, "reason"),
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	result = MSMEReturn(filters).run()

	if filters.view == DETAIL:
		return get_detail_columns(), result.detail
	return get_summary_columns(), result.summary


def validate_filters(filters):
	if not (filters.company and filters.from_date and filters.to_date):
		frappe.throw(_("Company, From Date and To Date are required."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_summary_columns():
	def pair(prefix, label):
		return [
			{"fieldname": f"{prefix}_no", "label": _("{0} - No.").format(label), "fieldtype": "Int", "width": 90},
			{"fieldname": f"{prefix}_amt", "label": _("{0} - Amount").format(label), "fieldtype": "Currency", "width": 140},
		]

	return [
		{"fieldname": "sno", "label": _("(a) S.No."), "fieldtype": "Data", "width": 70},
		{"fieldname": "supplier_name", "label": _("(b) Name of MSE Supplier"), "fieldtype": "Data", "width": 240},
		{"fieldname": "pan", "label": _("(c) PAN"), "fieldtype": "Data", "width": 110},
		*pair("tr", _("(d)(i) Paid within 45 days via TReDS")),
		*pair("other", _("(d)(ii) Paid within 45 days, other modes")),
		*pair("late", _("(e) Paid after 45 days")),
		*pair("out_le", _("(f) Outstanding 45 days or less")),
		*pair("out_gt", _("(g) Outstanding more than 45 days")),
		{"fieldname": "reason", "label": _("(h) Reason for delay"), "fieldtype": "Data", "width": 160},
		{"fieldname": "msme_type", "label": _("MSME Type"), "fieldtype": "Data", "width": 80},
		{"fieldname": "supplier", "label": _("Supplier ID"), "fieldtype": "Link", "options": "Supplier", "width": 130},
	]


def get_detail_columns():
	return [
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 130},
		{"fieldname": "supplier_name", "label": _("Supplier Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "pan", "label": _("PAN"), "fieldtype": "Data", "width": 105},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "voucher_no",
			"label": _("Invoice / Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{"fieldname": "bill_no", "label": _("Supplier Invoice No"), "fieldtype": "Data", "width": 130},
		{"fieldname": "bill_date", "label": _("Invoice Date (Ageing)"), "fieldtype": "Date", "width": 110},
		{"fieldname": "amount", "label": _("Invoice Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "open_at_start", "label": _("Unpaid at Period Start"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid_within", "label": _("Paid within 45 Days"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid_after", "label": _("Paid after 45 Days"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "adjusted", "label": _("Debit Notes / Adjusted"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "outstanding", "label": _("Outstanding at Period End"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "age_days", "label": _("Age at Period End (Days)"), "fieldtype": "Data", "width": 110},
		{"fieldname": "bucket", "label": _("MSME-1 Column"), "fieldtype": "Data", "width": 170},
		{
			"fieldname": "erp_outstanding",
			"label": _("ERPNext Outstanding (Today)"),
			"fieldtype": "Currency",
			"width": 150,
		},
		{"fieldname": "settled_by", "label": _("Settled By (FIFO)"), "fieldtype": "Data", "width": 420},
	]


class MSMEReturn:
	def __init__(self, filters):
		self.filters = filters
		self.from_date = getdate(filters.from_date)
		self.to_date = getdate(filters.to_date)
		self.by_invoice_date = filters.ageing_based_on == "Supplier Invoice Date"
		self.summary = []
		self.detail = []

	def run(self):
		suppliers = self.get_suppliers()
		if not suppliers:
			return self

		entries = self.get_ledger(list(suppliers))
		per_supplier = defaultdict(list)
		for e in entries:
			per_supplier[e.party].append(e)

		rows_by_pan = {}
		for name, info in sorted(suppliers.items(), key=lambda s: (s[1].supplier_name or s[0]).lower()):
			bills = fifo(per_supplier.get(name, []))
			row = self.summarise(info, bills)
			self.add_detail(info, bills)
			if not any(row[f] for f in AMOUNT_COLS):
				continue
			key = info.pan or name
			if key in rows_by_pan:  # the form allows one row per PAN
				merged = rows_by_pan[key]
				for f in AMOUNT_COLS + COUNT_COLS:
					merged[f] += row[f]
			else:
				rows_by_pan[key] = row

		for sno, row in enumerate(rows_by_pan.values(), 1):
			row["sno"] = sno
			for f in AMOUNT_COLS:
				row[f] = flt(row[f], 2)
			self.summary.append(row)
		return self

	def get_suppliers(self):
		types = {"Micro": ["Micro"], "Small": ["Small"]}.get(self.filters.msme_type, ["Micro", "Small"])
		filters = {"custom_msme_registered": "Yes", "custom_msme_type": ("in", types)}
		if self.filters.supplier:
			filters["name"] = self.filters.supplier
		return {
			s.name: s
			for s in frappe.get_all(
				"Supplier", filters=filters, fields=["name", "supplier_name", "pan", "custom_msme_type"]
			)
		}

	def get_ledger(self, suppliers):
		"""One net amount per voucher per supplier, up to period end, with what FIFO needs to know about it."""
		entries = frappe.db.sql(
			"""
			select gle.party, gle.voucher_type, gle.voucher_no, min(gle.posting_date) as posting_date,
				sum(gle.credit - gle.debit) as net
			from `tabGL Entry` gle
			where gle.party_type = 'Supplier' and gle.party in %(suppliers)s and gle.company = %(company)s
				and gle.is_cancelled = 0 and gle.posting_date <= %(to_date)s
			group by gle.party, gle.voucher_type, gle.voucher_no
			having abs(sum(gle.credit - gle.debit)) >= 0.005
			""",
			{"suppliers": suppliers, "company": self.filters.company, "to_date": self.to_date},
			as_dict=True,
		)

		names = defaultdict(set)
		for e in entries:
			names[e.voucher_type].add(e.voucher_no)
		invoices = get_details(
			"Purchase Invoice", names, ["name", "bill_no", "bill_date", "is_return", "outstanding_amount"]
		)
		payments = get_details("Payment Entry", names, ["name", "mode_of_payment"])
		journals = get_details("Journal Entry", names, ["name", "voucher_type"])
		# A journal that also touches a customer sets the supplier off against what they owe us.
		contra = set(
			frappe.get_all(
				"Journal Entry Account",
				filters={"parent": ("in", list(names["Journal Entry"]) or [""]), "party_type": "Customer"},
				pluck="parent",
			)
		)
		# Money in or out through a bank or cash account: a credit is the supplier paying us back, never a bill.
		banked = set(
			frappe.db.sql_list(
				"""
				select distinct jea.parent
				from `tabJournal Entry Account` jea
				join `tabAccount` acc on acc.name = jea.account
				where jea.parent in %(names)s and acc.account_type in ('Bank', 'Cash')
				""",
				{"names": list(names["Journal Entry"]) or [""]},
			)
		)

		for e in entries:
			e.net = flt(e.net, 2)
			e.date = getdate(e.posting_date)
			e.bill_date = e.date
			if e.voucher_type == "Purchase Invoice":
				pi = invoices.get(e.voucher_no) or frappe._dict()
				e.bill_no = pi.bill_no
				e.erp_outstanding = flt(pi.outstanding_amount)  # as ERPNext's own allocations leave it
				if self.by_invoice_date and pi.bill_date:
					e.bill_date = getdate(pi.bill_date)
				e.kind = "adjustment" if e.net < 0 else "invoice"
			elif e.voucher_type == "Payment Entry":
				mode = (payments.get(e.voucher_no) or {}).get("mode_of_payment") or ""
				e.treds = "treds" in mode.lower()
				e.kind = "payment" if e.net < 0 else "refund"
			elif e.voucher_type == "Journal Entry":
				je_type = (journals.get(e.voucher_no) or {}).get("voucher_type")
				if e.voucher_no in contra or e.voucher_no in banked:
					# Set-off or bank/cash: a debit settles bills like a payment; a credit takes earlier payments back.
					e.kind = "refund" if e.net > 0 else "payment"
				elif e.net > 0:
					e.kind = "invoice"  # bills and opening balances booked by journal
				elif je_type in ("Debit Note", "Credit Note"):
					e.kind = "adjustment"
				else:
					e.kind = "payment"  # bank/cash payments and TDS deducted are both settlement
			else:
				e.kind = "invoice" if e.net > 0 else "adjustment"
		return entries

	def summarise(self, info, bills):
		row = {
			"supplier": info.name,
			"supplier_name": info.supplier_name or info.name,
			"pan": (info.pan or "").upper(),
			"msme_type": info.custom_msme_type,
			"reason": self.filters.reason or ".",
		}
		counted = defaultdict(int)
		amounts = defaultdict(float)
		for bill in bills:
			if bill.kind != "invoice":
				continue
			for col, amount in self.columns(bill).items():
				counted[col] += 1
				amounts[col] += amount

		for col in COLUMNS:
			row[f"{col}_no"] = counted[col]
			row[f"{col}_amt"] = flt(amounts[col], 2)
		return row

	def columns(self, bill):
		"""How much of one invoice falls in each MSME-1 column for the period.

		A column gets the invoice only for more than a rupee: paise settled by a rounding
		entry must not count it as one more invoice paid.
		"""
		amounts = defaultdict(float)
		for a in bill.allocations:
			if a.kind != "payment" or not (self.from_date <= a.date <= self.to_date):
				continue
			if date_diff(a.get("paid_on") or a.date, bill.bill_date) <= CREDIT_DAYS:
				amounts["tr" if a.treds else "other"] += a.amount
			else:
				amounts["late"] += a.amount

		open_amt = bill.open_on(self.to_date)
		amounts["out_le" if date_diff(self.to_date, bill.bill_date) <= CREDIT_DAYS else "out_gt"] += open_amt
		return {col: amount for col, amount in amounts.items() if amount > TOLERANCE}

	def add_detail(self, info, bills):
		for bill in bills:
			if bill.kind != "invoice":
				continue
			in_period = [a for a in bill.allocations if self.from_date <= a.date <= self.to_date]
			cols = self.columns(bill)
			adjusted = sum(a.amount for a in in_period if a.kind != "payment")
			if not cols and adjusted <= TOLERANCE:
				continue

			paid_within = cols.get("tr", 0.0) + cols.get("other", 0.0)
			paid_after = cols.get("late", 0.0)
			outstanding = cols.get("out_le", cols.get("out_gt", 0.0))
			age = date_diff(self.to_date, bill.bill_date)
			if "out_le" in cols:
				bucket = _("(f) Outstanding ≤ 45 days")
			elif "out_gt" in cols:
				bucket = _("(g) Outstanding > 45 days")
			else:
				bucket = ""

			self.detail.append(
				{
					"supplier": info.name,
					"supplier_name": info.supplier_name,
					"pan": info.pan,
					"voucher_type": bill.voucher_type,
					"voucher_no": bill.voucher_no,
					"bill_no": bill.bill_no,
					"bill_date": bill.bill_date,
					"amount": bill.net,
					"open_at_start": flt(bill.open_on(self.from_date, before=True), 2),
					"paid_within": flt(paid_within, 2),
					"paid_after": flt(paid_after, 2),
					"adjusted": flt(adjusted, 2),
					"outstanding": flt(outstanding, 2),
					"age_days": age if bucket else None,
					"bucket": bucket,
					"erp_outstanding": bill.get("erp_outstanding"),
					"settled_by": ", ".join(
						f"{a.voucher_no} ({a.date.strftime('%d-%m-%y')}) {a.amount:,.2f}"
						+ (_(" reversed") if a.amount < 0 else "")
						for a in in_period
					),
				}
			)


def get_details(doctype, names, fields):
	if not names.get(doctype):
		return {}
	return {
		d.name: d for d in frappe.get_all(doctype, filters={"name": ("in", list(names[doctype]))}, fields=fields)
	}


class Bill(frappe._dict):
	def open_on(self, date, before=False):
		"""What was still unpaid at the end of `date` (or at its start, with before=True)."""
		if (self.date >= date) if before else (self.date > date):
			return 0.0
		settled = sum(a.amount for a in self.allocations if (a.date < date if before else a.date <= date))
		return max(self.net - settled, 0.0)


def fifo(entries):
	"""Settle bills oldest-first with every payment, adjustment and advance, as they happen.

	Bills (net credits) wait in a queue ordered by their ageing date; each settlement (net debit)
	pays off the head of that queue. Money paid before there is a bill to settle waits as an
	advance and is used up by the next bills, which then count as settled on the day they arrive.

	A refund or set-off credit means money already paid to the supplier was taken back or moved to
	their customer account. It first cancels unused advances, then undoes the most recent payments
	(last in, first out), so the invoices those payments covered are unpaid again from that day.
	"""
	bills = []
	open_bills = []  # sorted by (bill_date, date, voucher_no, index)
	advances = []  # [entry, remaining], oldest first
	paid = []  # payment allocations on invoices, in the order they were made

	def reopen(bill):
		if not bill.is_open:
			bill.is_open = True
			bisect.insort(open_bills, (bill.bill_date, bill.date, bill.voucher_no, bill.index))

	def settle(bill, credit, amount, date, **extra):
		allocation = frappe._dict(
			{
				"voucher_no": credit.voucher_no,
				"kind": credit.kind,
				"treds": credit.get("treds"),
				"amount": amount,
				"date": date,
				"undone": 0.0,
				**extra,
			}
		)
		bill.allocations.append(allocation)
		bill.remaining = flt(bill.remaining - amount, 2)
		if bill.kind == "invoice" and allocation.kind == "payment" and amount > 0:
			paid.append((bill, allocation))

	def undo_payments(refund):
		"""Take money back from the latest payments still standing."""
		while paid and refund.remaining > 0:
			bill, original = paid[-1]
			amount = min(original.amount - original.undone, refund.remaining)
			original.undone = flt(original.undone + amount, 2)
			# Classified as the payment it reverses, so it nets off in that payment's column.
			settle(bill, refund, -amount, refund.date, kind="payment", treds=original.treds, paid_on=original.date)
			settle(refund, frappe._dict(voucher_no=original.voucher_no, kind="payment"), amount, refund.date)
			reopen(bill)
			if original.undone >= original.amount:
				paid.pop()

	# Bills before settlements on the same day, so a same-day payment can clear that day's bill.
	for e in sorted(entries, key=lambda e: (e.date, 0 if e.net > 0 else 1, e.voucher_no)):
		if e.net > 0:
			bill = Bill(e, remaining=e.net, allocations=[], index=len(bills), is_open=False)
			bills.append(bill)
			# A refund cancels the newest advance first; a new bill uses up the oldest.
			while advances and bill.remaining > 0:
				credit = advances[-1] if bill.kind == "refund" else advances[0]
				amount = min(credit[1], bill.remaining)
				settle(bill, credit[0], amount, e.date)
				credit[1] = flt(credit[1] - amount, 2)
				if credit[1] <= 0:
					advances.remove(credit)
			if bill.kind == "refund":
				undo_payments(bill)
			if bill.remaining > 0:
				reopen(bill)
		else:
			left = -e.net
			while open_bills and left > 0:
				bill = bills[open_bills[0][3]]
				amount = min(left, bill.remaining)
				settle(bill, e, amount, e.date)
				left = flt(left - amount, 2)
				if bill.remaining <= 0:
					bill.is_open = False
					open_bills.pop(0)
			if left > 0:
				advances.append([e, left])
	return bills


@frappe.whitelist()
def download_msme_excel(filters):
	"""The MCA MSME-1 template with this period's rows filled in; every other part is left untouched."""
	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	filters.view = SUMMARY
	if not frappe.get_doc("Report", SUMMARY).is_permitted():
		frappe.throw(_("You are not permitted to download the MSME-1 return."), frappe.PermissionError)

	_columns, rows = execute(filters)
	with open(TEMPLATE, "rb") as f:
		content = fill_template(f.read(), rows)

	frappe.response["filename"] = f"MSME-1_{filters.from_date}_to_{filters.to_date}.xlsx"
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"


def fill_template(template, rows):
	src = zipfile.ZipFile(io.BytesIO(template))
	sheet = src.read(SHEET).decode("utf-8")

	if len(rows) > TOTAL_ROW - FIRST_ROW:
		frappe.throw(_("The MSME-1 template holds at most {0} suppliers.").format(TOTAL_ROW - FIRST_ROW))

	def replace(m):
		r = int(m.group(1))
		if r == TOTAL_ROW:
			return set_totals(m.group(0), rows)
		if r < FIRST_ROW or r > TOTAL_ROW:
			return m.group(0)  # header rows stay exactly as MCA made them
		i = r - FIRST_ROW
		return row_xml(r, rows[i]) if i < len(rows) else empty_row(r)

	sheet = re.sub(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', replace, sheet, flags=re.S)

	out = io.BytesIO()
	with zipfile.ZipFile(out, "w") as dst:
		for item in src.infolist():
			data = sheet.encode("utf-8") if item.filename == SHEET else src.read(item.filename)
			dst.writestr(item, data, compress_type=item.compress_type)
	return out.getvalue()


def row_xml(r, row):
	cells = []
	for col, style, field in ROW_LAYOUT:
		value = row.get(field)
		ref = f"{col}{r}"
		if field in ("supplier_name", "pan", "reason"):
			cells.append(
				f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value or ""))}</t></is></c>'
			)
		else:
			cells.append(f'<c r="{ref}" s="{style}"><v>{number(value)}</v></c>')
	return f'<row r="{r}" spans="1:14" x14ac:dyDescent="0.3">{"".join(cells)}</row>'


def empty_row(r):
	return f'<row r="{r}" spans="1:14" x14ac:dyDescent="0.3"/>'


def set_totals(total_row, rows):
	"""Refresh the cached results of the template's Total formulas so the file reads right before recalculation."""
	for col, _style, field in ROW_LAYOUT[3:13]:
		total = sum(flt(r.get(field)) for r in rows)
		if field.endswith("_amt"):  # as Excel's ROUND(...,0): halves go up, not to even
			total = int(Decimal(str(total)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
		total_row = re.sub(
			rf'(<c r="{col}{TOTAL_ROW}"[^>]*>.*?</f>)<v>[^<]*</v>',
			lambda m, t=total: f"{m.group(1)}<v>{number(t)}</v>",
			total_row,
			flags=re.S,
		)
	return total_row


def number(value):
	value = flt(value, 2)
	return str(cint(value)) if value == cint(value) else f"{value:.2f}"
