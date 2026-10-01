import frappe
from frappe import _
from frappe.utils import flt

# Stock Entry purposes that turn input batches into output batches.
PRODUCTION_PURPOSES = ("Manufacture", "Repack")
TRANSFER_PURPOSES = ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor")
MAX_DEPTH = 10
MAX_ROWS = 5000

PARTY_FIELDS = {
	"Purchase Receipt": "supplier_name",
	"Purchase Invoice": "supplier_name",
	"Delivery Note": "customer_name",
	"Sales Invoice": "customer_name",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.batch_no and not (filters.from_date and filters.to_date):
		frappe.throw(_("Select a Batch, or a From Date and To Date to trace the batches of that period."))

	return get_columns(), BatchTraceability(filters).run()


def get_columns():
	return [
		{"fieldname": "journey", "label": _("Journey"), "fieldtype": "Data", "width": 260},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 190},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"fieldname": "party", "label": _("Supplier / Customer"), "fieldtype": "Data", "width": 190},
		{
			"fieldname": "from_warehouse",
			"label": _("From Store"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"fieldname": "to_warehouse",
			"label": _("To Store"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "balance_qty", "label": _("Batch Balance"), "fieldtype": "Float", "width": 110},
		{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 100},
	]


class BatchTraceability:
	"""Builds a tree of batch movements, linking batches through production Stock Entries.

	Forward:  batch -> its movements -> batches produced from it -> their movements ... -> customer.
	Backward: batch -> its movements -> batches consumed to make it -> their movements ... -> supplier.
	"""

	def __init__(self, filters):
		self.filters = filters
		self.forward = filters.direction != "Backward"
		self.movements = {}  # batch_no -> grouped movements, oldest first
		self.batch_info = {}
		self.se_purpose = {}
		self.voucher_lines = {}  # production stock entry -> grouped lines (batched or not)
		self.data = []
		self.truncated = False

	def run(self):
		if self.filters.batch_no:
			roots = [self.filters.batch_no]
			self.load_batches(roots)
		else:
			roots = self.get_root_batches()
			self.load_batches(roots)
			roots = self.drop_nested_roots(roots)

		for batch_no in roots:
			self.add_batch(batch_no, 0, frozenset())

		if self.truncated:
			frappe.msgprint(
				_("Only the first {0} rows are shown. Narrow the filters to see the full journey.").format(
					MAX_ROWS
				),
				indicator="orange",
			)

		self.set_names()
		return self.data

	def get_root_batches(self):
		"""Batches (of the item, or of every item) whose first stock movement falls in the date range."""
		item_condition = "and sle.item_code = %(item_code)s" if self.filters.item_code else ""
		company_condition = "and sle.company = %(company)s" if self.filters.company else ""
		return frappe.db.sql_list(
			f"""
			select batch_no from (
				select sbe.batch_no, sle.posting_date
				from `tabStock Ledger Entry` sle
				inner join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
				where sle.is_cancelled = 0 and sbe.batch_no is not null {item_condition} {company_condition}

				union all

				select sle.batch_no, sle.posting_date
				from `tabStock Ledger Entry` sle
				where sle.is_cancelled = 0 and ifnull(sle.serial_and_batch_bundle, '') = ''
					and ifnull(sle.batch_no, '') != '' {item_condition} {company_condition}
			) t
			group by batch_no
			having min(posting_date) between %(from_date)s and %(to_date)s
			order by min(posting_date), batch_no
			""",
			self.filters,
		)

	def drop_nested_roots(self, roots):
		"""Leave out a batch that will already appear nested under another listed batch.

		Going forward, a finished batch made from a listed raw material batch shows up under it;
		going backward, a raw material batch consumed into a listed finished batch does.
		"""
		production = {
			m.voucher_no
			for b in roots
			for m in self.movements[b]
			if self.se_purpose.get(m.voucher_no) in PRODUCTION_PURPOSES
		}
		self.load_voucher_lines(production)

		root_set = set(roots)
		parents = {b: set() for b in roots}
		for lines in (self.voucher_lines[se] for se in production):
			sources = {l.batch_no for l in lines if l.batch_no in root_set and self.is_link(l)}
			for l in lines:
				if l.batch_no in root_set and self.is_linked_line(l):
					parents[l.batch_no] |= sources - {l.batch_no}

		# Two batches that each lead to the other would both vanish; keep both of those.
		return [b for b in roots if not any(b not in parents[p] for p in parents[b])]

	def load_batches(self, batches):
		batches = [b for b in set(batches) if b and b not in self.movements]
		if not batches:
			return

		rows = get_ledger_rows(
			"sbe.batch_no in %(batches)s",
			"sle.batch_no in %(batches)s",
			{"batches": batches},
			self.filters.company,
		)
		for batch_no in batches:
			self.movements[batch_no] = []
		for m in group_movements(rows):
			self.movements[m.batch_no].append(m)

		for b in frappe.get_all(
			"Batch",
			filters={"name": ("in", batches)},
			fields=[
				"name",
				"item",
				"stock_uom",
				"manufacturing_date",
				"expiry_date",
				"reference_doctype",
				"reference_name",
			],
		):
			self.batch_info[b.name] = b

		self.load_purposes(
			{m.voucher_no for b in batches for m in self.movements[b] if m.voucher_type == "Stock Entry"}
		)

	def load_purposes(self, stock_entries):
		stock_entries = [se for se in stock_entries if se not in self.se_purpose]
		if stock_entries:
			self.se_purpose.update(
				dict(
					frappe.get_all(
						"Stock Entry", filters={"name": ("in", stock_entries)}, fields=["name", "purpose"], as_list=1
					)
				)
			)

	def load_voucher_lines(self, stock_entries):
		stock_entries = [se for se in set(stock_entries) if se not in self.voucher_lines]
		if not stock_entries:
			return

		rows = get_ledger_rows(
			"sle.voucher_type = 'Stock Entry' and sle.voucher_no in %(vouchers)s",
			"sle.voucher_type = 'Stock Entry' and sle.voucher_no in %(vouchers)s",
			{"vouchers": stock_entries},
		)
		for se in stock_entries:
			self.voucher_lines[se] = []
		for line in group_movements(rows):
			self.voucher_lines[line.voucher_no].append(line)

	def add_batch(self, batch_no, indent, ancestors):
		if not self.has_room():
			return

		info = self.batch_info.get(batch_no) or frappe._dict(name=batch_no)
		movements = self.movements.get(batch_no, [])
		self.data.append(
			{
				"journey": _("Batch {0}").format(batch_no),
				"is_batch": 1,
				"indent": indent,
				"batch_no": batch_no,
				"item_code": info.item or (movements[0].item_code if movements else None),
				"posting_date": info.manufacturing_date,
				"voucher_type": info.reference_doctype,
				"voucher_no": info.reference_name,
				"qty": sum(m.qty for m in movements if m.qty > 0 and not m.is_transfer),
				"uom": info.stock_uom or (movements[0].stock_uom if movements else None),
				"balance_qty": sum(m.net_qty for m in movements),
				"expiry_date": info.expiry_date,
			}
		)

		if batch_no in ancestors:
			self.data[-1]["journey"] = _("Batch {0} (repeats, see above)").format(batch_no)
			return

		ancestors = ancestors | {batch_no}
		links = [m for m in movements if self.is_link(m)]
		link_ids = {id(m) for m in links}
		self.load_voucher_lines(m.voucher_no for m in links)

		linked_batches = set()
		for m in links:
			for line in self.voucher_lines.get(m.voucher_no, []):
				if line.batch_no and self.is_linked_line(line):
					linked_batches.add(line.batch_no)
		self.load_batches(linked_batches)

		for m in movements:
			if not self.has_room():
				return
			self.data.append(self.movement_row(m, indent + 1))
			if id(m) in link_ids:
				self.add_linked(m, indent + 2, ancestors)

	def add_linked(self, movement, indent, ancestors):
		"""Under a production movement, add the batches on the other side of that Stock Entry."""
		if indent // 2 > MAX_DEPTH:
			return

		seen = set()
		for line in self.voucher_lines.get(movement.voucher_no, []):
			if not self.is_linked_line(line) or not self.has_room():
				continue
			if line.batch_no:
				if line.batch_no not in seen:
					seen.add(line.batch_no)
					self.add_batch(line.batch_no, indent, ancestors)
			else:
				row = self.movement_row(line, indent)
				row["journey"] = (
					_("Produced (no batch)") if line.net_qty > 0 else _("Consumed (no batch)")
				)
				self.data.append(row)

	def is_link(self, m):
		"""A movement that leads to other batches in the chosen direction."""
		if m.voucher_type != "Stock Entry" or self.se_purpose.get(m.voucher_no) not in PRODUCTION_PURPOSES:
			return False
		return m.net_qty < 0 if self.forward else m.net_qty > 0

	def is_linked_line(self, line):
		"""The lines on the far side of a production entry: outputs going forward, inputs going back."""
		return line.net_qty > 0 if self.forward else line.net_qty < 0

	def movement_row(self, m, indent):
		return {
			"journey": self.get_stage(m),
			"indent": indent,
			"batch_no": m.batch_no,
			"item_code": m.item_code,
			"posting_date": m.posting_date,
			"voucher_type": m.voucher_type,
			"voucher_no": m.voucher_no,
			"from_warehouse": m.from_warehouse,
			"to_warehouse": m.to_warehouse,
			"qty": m.qty,
			"uom": m.stock_uom,
		}

	def get_stage(self, m):
		inward = m.net_qty > 0
		if m.voucher_type in ("Purchase Receipt", "Purchase Invoice"):
			return _("Received from Supplier") if inward else _("Returned to Supplier")
		if m.voucher_type in ("Delivery Note", "Sales Invoice"):
			return _("Dispatched to Customer") if not inward else _("Returned by Customer")
		if m.voucher_type == "Stock Entry":
			purpose = self.se_purpose.get(m.voucher_no)
			if m.is_transfer or purpose in TRANSFER_PURPOSES:
				return _("Transferred")
			if purpose in PRODUCTION_PURPOSES:
				return _("Produced") if inward else _("Consumed in Production")
			if purpose == "Material Receipt":
				return _("Stock Received")
			if purpose == "Material Issue":
				return _("Stock Issued")
			return _(purpose or m.voucher_type)
		if m.voucher_type == "Stock Reconciliation":
			return _("Stock Reconciliation")
		return _(m.voucher_type)

	def has_room(self):
		if len(self.data) >= MAX_ROWS:
			self.truncated = True
			return False
		return True

	def set_names(self):
		items = {r["item_code"] for r in self.data if r.get("item_code")}
		item_names = dict(
			frappe.get_all("Item", filters={"name": ("in", list(items))}, fields=["name", "item_name"], as_list=1)
		) if items else {}

		parties = {}
		for voucher_type, field in PARTY_FIELDS.items():
			names = {r["voucher_no"] for r in self.data if r.get("voucher_type") == voucher_type}
			if names:
				for name, party in frappe.get_all(
					voucher_type, filters={"name": ("in", list(names))}, fields=["name", field], as_list=1
				):
					parties[(voucher_type, name)] = party

		for r in self.data:
			r["item_name"] = item_names.get(r.get("item_code"))
			r["party"] = parties.get((r.get("voucher_type"), r.get("voucher_no")))


def get_ledger_rows(bundle_condition, legacy_condition, values, company=None):
	"""Batch-wise stock ledger rows, reading both Serial and Batch Bundles and the legacy batch_no field."""
	company_condition = "and sle.company = %(company)s" if company else ""
	return frappe.db.sql(
		f"""
		select sle.posting_date, sle.posting_time, sle.creation, sle.voucher_type, sle.voucher_no,
			sle.voucher_detail_no, sle.item_code, sle.warehouse, sle.stock_uom,
			sbe.batch_no, sbe.qty
		from `tabStock Ledger Entry` sle
		inner join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
		where sle.is_cancelled = 0 and {bundle_condition} {company_condition}

		union all

		select sle.posting_date, sle.posting_time, sle.creation, sle.voucher_type, sle.voucher_no,
			sle.voucher_detail_no, sle.item_code, sle.warehouse, sle.stock_uom,
			nullif(sle.batch_no, ''), sle.actual_qty
		from `tabStock Ledger Entry` sle
		where sle.is_cancelled = 0 and ifnull(sle.serial_and_batch_bundle, '') = ''
			and {legacy_condition} {company_condition}
		""",
		{**values, "company": company},
		as_dict=1,
	)


def group_movements(rows):
	"""One movement per voucher line and batch; the two legs of a transfer become one from -> to row."""
	grouped = {}
	for r in rows:
		key = (r.voucher_type, r.voucher_no, r.voucher_detail_no, r.batch_no or None, r.item_code)
		m = grouped.get(key)
		if not m:
			m = grouped[key] = frappe._dict(
				r, batch_no=r.batch_no or None, in_qty=0.0, out_qty=0.0, from_warehouse=None, to_warehouse=None
			)
		qty = flt(r.qty)
		if qty > 0:
			m.in_qty += qty
			m.to_warehouse = m.to_warehouse or r.warehouse
		else:
			m.out_qty -= qty
			m.from_warehouse = m.from_warehouse or r.warehouse

	movements = list(grouped.values())
	for m in movements:
		m.is_transfer = bool(m.in_qty and m.out_qty)
		m.net_qty = m.in_qty - m.out_qty
		m.qty = m.in_qty if m.is_transfer else m.net_qty
	return sorted(movements, key=lambda m: (m.posting_date, m.posting_time, m.creation))
