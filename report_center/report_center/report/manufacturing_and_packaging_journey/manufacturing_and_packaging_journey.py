import frappe
from frappe import _
from frappe.utils import flt, cstr, getdate

MAX_ROWS = 5000

def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") and not filters.get("batch_no") and not filters.get("stock_entry"):
		filters["from_date"] = frappe.utils.add_months(frappe.utils.nowdate(), -1)
	if not filters.get("to_date") and not filters.get("batch_no") and not filters.get("stock_entry"):
		filters["to_date"] = frappe.utils.nowdate()
	view_mode = filters.get("view_mode") or "Hierarchical Journey Tree"
	
	columns = get_columns(view_mode)
	engine = ManufacturingJourneyEngine(filters)
	data, report_summary, chart = engine.run(view_mode)
	
	return columns, data, None, chart, report_summary


def get_columns(view_mode="Hierarchical Journey Tree"):
	if view_mode == "Batch Lineage Matrix":
		return [
			{"fieldname": "stage1_se", "label": _("Stage 1 SE (Loose)"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
			{"fieldname": "stage1_date", "label": _("Stage 1 Date"), "fieldtype": "Date", "width": 95},
			{"fieldname": "stage1_user", "label": _("Stage 1 Created By"), "fieldtype": "Data", "width": 140},
			{"fieldname": "rm_summary", "label": _("RM Consumed (Items & Batches)"), "fieldtype": "Data", "width": 220},
			{"fieldname": "rm_cost", "label": _("RM Total Cost"), "fieldtype": "Currency", "width": 110},
			{"fieldname": "loose_item_code", "label": _("Loose Item"), "fieldtype": "Link", "options": "Item", "width": 120},
			{"fieldname": "loose_item_name", "label": _("Loose Item Name"), "fieldtype": "Data", "width": 160},
			{"fieldname": "loose_batch_no", "label": _("Loose Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
			{"fieldname": "loose_qty_produced", "label": _("Loose Qty Produced"), "fieldtype": "Float", "width": 110},
			{"fieldname": "loose_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 60},
			{"fieldname": "loose_rate", "label": _("Loose Rate"), "fieldtype": "Currency", "width": 95},
			{"fieldname": "loose_val", "label": _("Loose Value"), "fieldtype": "Currency", "width": 110},
			{"fieldname": "loose_current_stock", "label": _("Loose WH Stock"), "fieldtype": "Float", "width": 105},
			{"fieldname": "stage2_se", "label": _("Stage 2 SE (Packaged)"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
			{"fieldname": "stage2_date", "label": _("Stage 2 Date"), "fieldtype": "Date", "width": 95},
			{"fieldname": "stage2_user", "label": _("Stage 2 Created By"), "fieldtype": "Data", "width": 140},
			{"fieldname": "stage2_bom", "label": _("Stage 2 BOM"), "fieldtype": "Link", "options": "BOM", "width": 140},
			{"fieldname": "loose_qty_consumed", "label": _("Loose Qty Consumed"), "fieldtype": "Float", "width": 110},
			{"fieldname": "packaging_summary", "label": _("Packaging Materials"), "fieldtype": "Data", "width": 200},
			{"fieldname": "packaging_cost", "label": _("Packaging Cost"), "fieldtype": "Currency", "width": 110},
			{"fieldname": "fg_item_code", "label": _("FG Item"), "fieldtype": "Link", "options": "Item", "width": 120},
			{"fieldname": "fg_item_name", "label": _("FG Item Name"), "fieldtype": "Data", "width": 170},
			{"fieldname": "fg_batch_no", "label": _("FG Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
			{"fieldname": "fg_qty_produced", "label": _("FG Qty Produced"), "fieldtype": "Float", "width": 110},
			{"fieldname": "fg_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 60},
			{"fieldname": "fg_rate", "label": _("FG Rate"), "fieldtype": "Currency", "width": 95},
			{"fieldname": "fg_value", "label": _("FG Value"), "fieldtype": "Currency", "width": 110},
			{"fieldname": "fg_current_stock", "label": _("FG WH Stock"), "fieldtype": "Float", "width": 105},
		]
	elif view_mode == "Loose Item Reconciliation Summary":
		return [
			{"fieldname": "loose_item_code", "label": _("Loose Item"), "fieldtype": "Link", "options": "Item", "width": 130},
			{"fieldname": "loose_item_name", "label": _("Loose Item Name"), "fieldtype": "Data", "width": 190},
			{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
			{"fieldname": "total_produced_qty", "label": _("Total Loose Produced"), "fieldtype": "Float", "width": 130},
			{"fieldname": "total_rm_cost", "label": _("Total RM Cost Incurred"), "fieldtype": "Currency", "width": 140},
			{"fieldname": "avg_rm_cost", "label": _("Avg RM Cost / Unit"), "fieldtype": "Currency", "width": 120},
			{"fieldname": "total_consumed_qty", "label": _("Total Loose Packaged"), "fieldtype": "Float", "width": 130},
			{"fieldname": "total_packaging_cost", "label": _("Total Packaging Cost Added"), "fieldtype": "Currency", "width": 140},
			{"fieldname": "total_fg_units", "label": _("Total FG Units Produced"), "fieldtype": "Float", "width": 130},
			{"fieldname": "total_fg_val", "label": _("Total FG Valuation"), "fieldtype": "Currency", "width": 140},
			{"fieldname": "unconverted_qty", "label": _("Unpackaged / Diff Qty"), "fieldtype": "Float", "width": 130},
			{"fieldname": "current_wh_stock", "label": _("Current Physical Stock"), "fieldtype": "Float", "width": 130},
			{"fieldname": "stock_discrepancy", "label": _("Variance / Yield Loss"), "fieldtype": "Float", "width": 130},
		]
	
	# Default: Hierarchical Journey Tree
	return [
		{"fieldname": "journey", "label": _("Journey / Stage"), "fieldtype": "Data", "width": 280},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "voucher_no", "label": _("Stock Entry No"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
		{"fieldname": "bom_no", "label": _("BOM No"), "fieldtype": "Link", "options": "BOM", "width": 150},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "batch_no", "label": _("Batch No"), "fieldtype": "Link", "options": "Batch", "width": 140},
		{"fieldname": "mfg_date", "label": _("Mfg Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "stage_type", "label": _("Classification"), "fieldtype": "Data", "width": 140},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 65},
		{"fieldname": "basic_rate", "label": _("Rate (₹)"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "amount", "label": _("Total Amount (₹)"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"fieldname": "current_batch_qty", "label": _("Batch Stock (WH)"), "fieldtype": "Float", "width": 110},
		{"fieldname": "current_wh_qty", "label": _("Total Item Stock (WH)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "created_by", "label": _("Created By"), "fieldtype": "Data", "width": 150},
	]


class ManufacturingJourneyEngine:
	def __init__(self, filters):
		self.filters = filters
		self.users = {}
		self.batches = {}
		self.bin_stock = {}
		self.batch_stock = {}
		self.loose_item_codes = set()
		self.load_initial_metadata()

	def load_initial_metadata(self):
		# Pre-cache user names
		for u in frappe.db.sql("SELECT name, full_name FROM `tabUser`", as_dict=True):
			self.users[u.name] = u.full_name or u.name

		# Pre-cache identified loose / sub-assembly items
		loose_q = frappe.db.sql("""
			SELECT DISTINCT p.item_code
			FROM `tabStock Entry Detail` p
			JOIN `tabStock Entry` se_p ON se_p.name = p.parent AND se_p.purpose = 'Manufacture' AND se_p.docstatus = 1
			JOIN `tabStock Entry Detail` c ON c.item_code = p.item_code AND c.is_finished_item = 0
			JOIN `tabStock Entry` se_c ON se_c.name = c.parent AND se_c.purpose = 'Manufacture' AND se_c.docstatus = 1
			WHERE p.is_finished_item = 1
		""", as_dict=True)
		self.loose_item_codes = {r.item_code for r in loose_q}

	def load_item_batch_stock(self, item_codes, batch_nos):
		if not item_codes:
			return

		# Targeted Bin stock
		bins = frappe.db.sql("""
			SELECT item_code, warehouse, actual_qty, stock_value
			FROM `tabBin`
			WHERE item_code IN %(item_codes)s
		""", {"item_codes": list(item_codes)}, as_dict=True)
		for b in bins:
			self.bin_stock[(b.item_code, b.warehouse)] = flt(b.actual_qty)

		# Targeted Batch details & SLE stock
		if batch_nos:
			batch_list = list(batch_nos)
			batches = frappe.db.sql("""
				SELECT name, item, manufacturing_date, expiry_date, batch_qty
				FROM `tabBatch`
				WHERE name IN %(batch_nos)s
			""", {"batch_nos": batch_list}, as_dict=True)
			for b in batches:
				self.batches[b.name] = b

			batch_sle = frappe.db.sql("""
				SELECT item_code, warehouse, batch_no, sum(actual_qty) as qty
				FROM `tabStock Ledger Entry`
				WHERE is_cancelled = 0 AND batch_no IN %(batch_nos)s
				GROUP BY item_code, warehouse, batch_no
			""", {"batch_nos": batch_list}, as_dict=True)
			for s in batch_sle:
				self.batch_stock[(s.item_code, s.warehouse, s.batch_no)] = flt(s.qty)

	def run(self, view_mode="Hierarchical Journey Tree"):
		stage1_entries, stage2_entries = self.fetch_production_entries()

		# Collect all items and batches involved to fetch stock in bulk with targeted indexing
		all_items = set()
		all_batches = set()
		for se in stage1_entries + stage2_entries:
			for item in se["finished_items"] + se["consumed_items"]:
				if item.item_code:
					all_items.add(item.item_code)
				if item.batch_no:
					all_batches.add(item.batch_no)

		self.load_item_batch_stock(all_items, all_batches)
		
		if view_mode == "Batch Lineage Matrix":
			return self.build_lineage_matrix(stage1_entries, stage2_entries)
		elif view_mode == "Loose Item Reconciliation Summary":
			return self.build_reconciliation_summary(stage1_entries, stage2_entries)
		else:
			return self.build_journey_tree(stage1_entries, stage2_entries)

	def fetch_production_entries(self):
		conditions = ["se.purpose = 'Manufacture'", "se.docstatus = 1"]
		values = {}

		if self.filters.get("company"):
			conditions.append("se.company = %(company)s")
			values["company"] = self.filters.company

		if self.filters.get("from_date"):
			conditions.append("se.posting_date >= %(from_date)s")
			values["from_date"] = self.filters.from_date

		if self.filters.get("to_date"):
			conditions.append("se.posting_date <= %(to_date)s")
			values["to_date"] = self.filters.to_date

		if self.filters.get("stock_entry"):
			conditions.append("se.name = %(stock_entry)s")
			values["stock_entry"] = self.filters.stock_entry

		if self.filters.get("created_by"):
			conditions.append("se.owner = %(created_by)s")
			values["created_by"] = self.filters.created_by

		where_clause = " AND ".join(conditions)

		query = f"""
			SELECT se.name as se_no, se.posting_date, se.posting_time, se.bom_no, se.owner, se.company,
			       sed.name as sed_name, sed.item_code, sed.item_name, sed.qty, sed.stock_uom,
			       sed.basic_rate, sed.amount, sed.is_finished_item, sed.s_warehouse, sed.t_warehouse,
			       sed.batch_no
			FROM `tabStock Entry` se
			JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE {where_clause}
			ORDER BY se.posting_date DESC, se.name DESC
		"""
		rows = frappe.db.sql(query, values, as_dict=True)

		se_grouped = {}
		for r in rows:
			se_no = r.se_no
			if se_no not in se_grouped:
				se_grouped[se_no] = {
					"se_no": se_no,
					"posting_date": r.posting_date,
					"posting_time": r.posting_time,
					"bom_no": r.bom_no,
					"owner": r.owner,
					"company": r.company,
					"finished_items": [],
					"consumed_items": []
				}
			if r.is_finished_item:
				se_grouped[se_no]["finished_items"].append(r)
			else:
				se_grouped[se_no]["consumed_items"].append(r)

		stage1_entries = []
		stage2_entries = []

		for se_no, se in se_grouped.items():
			produced_loose = [f for f in se["finished_items"] if f.item_code in self.loose_item_codes or (self.filters.loose_item_code and f.item_code == self.filters.loose_item_code)]
			consumed_loose = [c for c in se["consumed_items"] if c.item_code in self.loose_item_codes or (self.filters.loose_item_code and c.item_code == self.filters.loose_item_code)]

			if produced_loose:
				stage1_entries.append(se)
			if consumed_loose:
				stage2_entries.append(se)

			if not produced_loose and not consumed_loose:
				if self.filters.fg_item_code:
					if any(f.item_code == self.filters.fg_item_code for f in se["finished_items"]):
						stage2_entries.append(se)
				elif self.filters.rm_item_code:
					if any(c.item_code == self.filters.rm_item_code for c in se["consumed_items"]):
						stage1_entries.append(se)
				else:
					if se["finished_items"]:
						stage1_entries.append(se)

		if self.filters.batch_no:
			b_filter = self.filters.batch_no
			stage1_entries = [se for se in stage1_entries if any(f.batch_no == b_filter for f in se["finished_items"]) or any(c.batch_no == b_filter for c in se["consumed_items"])]
			stage2_entries = [se for se in stage2_entries if any(f.batch_no == b_filter for f in se["finished_items"]) or any(c.batch_no == b_filter for c in se["consumed_items"])]

		if self.filters.loose_item_code:
			l_filter = self.filters.loose_item_code
			stage1_entries = [se for se in stage1_entries if any(f.item_code == l_filter for f in se["finished_items"])]
			stage2_entries = [se for se in stage2_entries if any(c.item_code == l_filter for c in se["consumed_items"])]

		if self.filters.fg_item_code:
			fg_filter = self.filters.fg_item_code
			stage2_entries = [se for se in stage2_entries if any(f.item_code == fg_filter for f in se["finished_items"])]

		if self.filters.rm_item_code:
			rm_filter = self.filters.rm_item_code
			stage1_entries = [se for se in stage1_entries if any(c.item_code == rm_filter for c in se["consumed_items"])]

		return stage1_entries, stage2_entries

	def build_journey_tree(self, stage1_entries, stage2_entries):
		data = []
		tot_loose_qty = 0.0
		tot_rm_val = 0.0
		tot_fg_qty = 0.0
		tot_fg_val = 0.0
		tot_pack_val = 0.0
		loose_stock_set = set()

		stage2_by_loose_batch = {}
		stage2_by_loose_item = {}

		for se2 in stage2_entries:
			for c in se2["consumed_items"]:
				item = c.item_code
				batch = c.batch_no
				if batch:
					stage2_by_loose_batch.setdefault((item, batch), []).append((se2, c))
				stage2_by_loose_item.setdefault(item, []).append((se2, c))

		for se1 in stage1_entries:
			user_display = self.users.get(se1["owner"], se1["owner"])

			for fg1 in se1["finished_items"]:
				item_code = fg1.item_code
				batch_no = fg1.batch_no or ""
				wh = fg1.t_warehouse or ""
				b_info = self.batches.get(batch_no, {})
				
				wh_stock = self.bin_stock.get((item_code, wh), 0.0)
				b_stock = self.batch_stock.get((item_code, wh, batch_no), 0.0) if batch_no else wh_stock

				tot_loose_qty += flt(fg1.qty)
				loose_stock_set.add((item_code, wh))

				batch_label = f" [Batch: {batch_no}]" if batch_no else ""
				data.append({
					"journey": f"🔵 [Stage 1: Bulk Produced] {fg1.item_name or item_code}{batch_label}",
					"posting_date": se1["posting_date"],
					"voucher_type": "Stock Entry",
					"voucher_no": se1["se_no"],
					"bom_no": se1["bom_no"],
					"item_code": item_code,
					"item_name": fg1.item_name,
					"batch_no": batch_no,
					"mfg_date": b_info.get("manufacturing_date"),
					"expiry_date": b_info.get("expiry_date"),
					"stage_type": "Loose Produced",
					"qty": flt(fg1.qty),
					"uom": fg1.stock_uom,
					"basic_rate": flt(fg1.basic_rate),
					"amount": flt(fg1.amount),
					"warehouse": wh,
					"current_batch_qty": b_stock,
					"current_wh_qty": wh_stock,
					"created_by": user_display,
					"indent": 0
				})

				for rm in se1["consumed_items"]:
					tot_rm_val += flt(rm.amount)
					rm_b = rm.batch_no or ""
					rm_wh = rm.s_warehouse or ""
					rm_b_info = self.batches.get(rm_b, {})
					rm_wh_stock = self.bin_stock.get((rm.item_code, rm_wh), 0.0)
					rm_b_stock = self.batch_stock.get((rm.item_code, rm_wh, rm_b), 0.0) if rm_b else rm_wh_stock

					rm_batch_str = f" [B#{rm_b}]" if rm_b else ""
					data.append({
						"journey": f"  ↳ 🟠 [RM Consumed] {rm.item_name or rm.item_code}{rm_batch_str}",
						"posting_date": se1["posting_date"],
						"voucher_type": "Stock Entry",
						"voucher_no": se1["se_no"],
						"bom_no": se1["bom_no"],
						"item_code": rm.item_code,
						"item_name": rm.item_name,
						"batch_no": rm_b,
						"mfg_date": rm_b_info.get("manufacturing_date"),
						"expiry_date": rm_b_info.get("expiry_date"),
						"stage_type": "RM Input",
						"qty": flt(rm.qty),
						"uom": rm.stock_uom,
						"basic_rate": flt(rm.basic_rate),
						"amount": flt(rm.amount),
						"warehouse": rm_wh,
						"current_batch_qty": rm_b_stock,
						"current_wh_qty": rm_wh_stock,
						"created_by": user_display,
						"indent": 1
					})

				matched_se2 = []
				if batch_no and (item_code, batch_no) in stage2_by_loose_batch:
					matched_se2 = stage2_by_loose_batch[(item_code, batch_no)]
				elif item_code in stage2_by_loose_item:
					matched_se2 = [pair for pair in stage2_by_loose_item[item_code] if pair[0]["posting_date"] >= se1["posting_date"]]

				seen_se2 = set()
				for se2, c_line in matched_se2:
					if se2["se_no"] in seen_se2:
						continue
					seen_se2.add(se2["se_no"])

					se2_user = self.users.get(se2["owner"], se2["owner"])

					for fg2 in se2["finished_items"]:
						fg2_batch = fg2.batch_no or ""
						fg2_wh = fg2.t_warehouse or ""
						fg2_b_info = self.batches.get(fg2_batch, {})
						fg2_wh_stock = self.bin_stock.get((fg2.item_code, fg2_wh), 0.0)
						fg2_b_stock = self.batch_stock.get((fg2.item_code, fg2_wh, fg2_batch), 0.0) if fg2_batch else fg2_wh_stock

						tot_fg_qty += flt(fg2.qty)
						tot_fg_val += flt(fg2.amount)

						fg_batch_str = f" [B#{fg2_batch}]" if fg2_batch else ""
						data.append({
							"journey": f"  ↳ 🟢 [Stage 2: Packaged FG] {fg2.item_name or fg2.item_code}{fg_batch_str}",
							"posting_date": se2["posting_date"],
							"voucher_type": "Stock Entry",
							"voucher_no": se2["se_no"],
							"bom_no": se2["bom_no"],
							"item_code": fg2.item_code,
							"item_name": fg2.item_name,
							"batch_no": fg2_batch,
							"mfg_date": fg2_b_info.get("manufacturing_date"),
							"expiry_date": fg2_b_info.get("expiry_date"),
							"stage_type": "FG Produced",
							"qty": flt(fg2.qty),
							"uom": fg2.stock_uom,
							"basic_rate": flt(fg2.basic_rate),
							"amount": flt(fg2.amount),
							"warehouse": fg2_wh,
							"current_batch_qty": fg2_b_stock,
							"current_wh_qty": fg2_wh_stock,
							"created_by": se2_user,
							"indent": 1
						})

					for c_item in se2["consumed_items"]:
						c_batch = c_item.batch_no or ""
						c_wh = c_item.s_warehouse or ""
						c_b_info = self.batches.get(c_batch, {})
						c_wh_stock = self.bin_stock.get((c_item.item_code, c_wh), 0.0)
						c_b_stock = self.batch_stock.get((c_item.item_code, c_wh, c_batch), 0.0) if c_batch else c_wh_stock

						is_loose = (c_item.item_code == item_code)
						if is_loose:
							badge = "    ↳ 🔵 [Loose Consumed]"
							st_type = "Loose Consumed"
						else:
							badge = "    ↳ 🟣 [Packaging]"
							st_type = "Packaging Consumed"
							tot_pack_val += flt(c_item.amount)

						c_batch_str = f" [B#{c_batch}]" if c_batch else ""
						data.append({
							"journey": f"{badge} {c_item.item_name or c_item.item_code}{c_batch_str}",
							"posting_date": se2["posting_date"],
							"voucher_type": "Stock Entry",
							"voucher_no": se2["se_no"],
							"bom_no": se2["bom_no"],
							"item_code": c_item.item_code,
							"item_name": c_item.item_name,
							"batch_no": c_batch,
							"mfg_date": c_b_info.get("manufacturing_date"),
							"expiry_date": c_b_info.get("expiry_date"),
							"stage_type": st_type,
							"qty": flt(c_item.qty),
							"uom": c_item.stock_uom,
							"basic_rate": flt(c_item.basic_rate),
							"amount": flt(c_item.amount),
							"warehouse": c_wh,
							"current_batch_qty": c_b_stock,
							"current_wh_qty": c_wh_stock,
							"created_by": se2_user,
							"indent": 2
						})

		current_loose_stock = sum(self.bin_stock.get(key, 0.0) for key in loose_stock_set)

		report_summary = self.build_summary_cards(tot_loose_qty, tot_rm_val, tot_fg_qty, tot_fg_val, tot_pack_val, current_loose_stock)
		chart = self.build_chart(tot_rm_val, tot_pack_val, tot_fg_val)

		return data, report_summary, chart

	def build_lineage_matrix(self, stage1_entries, stage2_entries):
		data = []
		tot_loose_qty = 0.0
		tot_rm_val = 0.0
		tot_fg_qty = 0.0
		tot_fg_val = 0.0
		tot_pack_val = 0.0

		stage2_by_loose_item = {}
		stage2_by_loose_batch = {}
		for se2 in stage2_entries:
			for c in se2["consumed_items"]:
				if c.batch_no:
					stage2_by_loose_batch.setdefault((c.item_code, c.batch_no), []).append((se2, c))
				stage2_by_loose_item.setdefault(c.item_code, []).append((se2, c))

		for se1 in stage1_entries:
			se1_user = self.users.get(se1["owner"], se1["owner"])

			rm_parts = []
			rm_total = 0.0
			for rm in se1["consumed_items"]:
				rm_total += flt(rm.amount)
				b_str = f" (#{rm.batch_no})" if rm.batch_no else ""
				rm_parts.append(f"{rm.item_code}{b_str}: {rm.qty} {rm.stock_uom}")
			rm_summary = ", ".join(rm_parts)
			tot_rm_val += rm_total

			for fg1 in se1["finished_items"]:
				item_code = fg1.item_code
				batch_no = fg1.batch_no or ""
				wh = fg1.t_warehouse or ""
				wh_stock = self.bin_stock.get((item_code, wh), 0.0)
				tot_loose_qty += flt(fg1.qty)

				matched_se2 = []
				if batch_no and (item_code, batch_no) in stage2_by_loose_batch:
					matched_se2 = stage2_by_loose_batch[(item_code, batch_no)]
				elif item_code in stage2_by_loose_item:
					matched_se2 = [p for p in stage2_by_loose_item[item_code] if p[0]["posting_date"] >= se1["posting_date"]]

				if not matched_se2:
					data.append({
						"stage1_se": se1["se_no"],
						"stage1_date": se1["posting_date"],
						"stage1_user": se1_user,
						"rm_summary": rm_summary,
						"rm_cost": rm_total,
						"loose_item_code": item_code,
						"loose_item_name": fg1.item_name,
						"loose_batch_no": batch_no,
						"loose_qty_produced": flt(fg1.qty),
						"loose_uom": fg1.stock_uom,
						"loose_rate": flt(fg1.basic_rate),
						"loose_val": flt(fg1.amount),
						"loose_current_stock": wh_stock,
						"stage2_se": "",
						"stage2_date": None,
						"stage2_user": "",
						"stage2_bom": "",
						"loose_qty_consumed": 0.0,
						"packaging_summary": "-",
						"packaging_cost": 0.0,
						"fg_item_code": "-",
						"fg_item_name": "Unpackaged / In Stock",
						"fg_batch_no": "",
						"fg_qty_produced": 0.0,
						"fg_uom": "",
						"fg_rate": 0.0,
						"fg_value": 0.0,
						"fg_current_stock": 0.0
					})
				else:
					for se2, c_line in matched_se2:
						se2_user = self.users.get(se2["owner"], se2["owner"])

						pack_parts = []
						pack_total = 0.0
						for p in se2["consumed_items"]:
							if p.item_code != item_code:
								pack_total += flt(p.amount)
								pack_parts.append(f"{p.item_name or p.item_code}: {p.qty}")
						pack_summary = ", ".join(pack_parts)
						tot_pack_val += pack_total

						for fg2 in se2["finished_items"]:
							fg2_wh = fg2.t_warehouse or ""
							fg2_stock = self.bin_stock.get((fg2.item_code, fg2_wh), 0.0)
							tot_fg_qty += flt(fg2.qty)
							tot_fg_val += flt(fg2.amount)

							data.append({
								"stage1_se": se1["se_no"],
								"stage1_date": se1["posting_date"],
								"stage1_user": se1_user,
								"rm_summary": rm_summary,
								"rm_cost": rm_total,
								"loose_item_code": item_code,
								"loose_item_name": fg1.item_name,
								"loose_batch_no": batch_no,
								"loose_qty_produced": flt(fg1.qty),
								"loose_uom": fg1.stock_uom,
								"loose_rate": flt(fg1.basic_rate),
								"loose_val": flt(fg1.amount),
								"loose_current_stock": wh_stock,
								"stage2_se": se2["se_no"],
								"stage2_date": se2["posting_date"],
								"stage2_user": se2_user,
								"stage2_bom": se2["bom_no"],
								"loose_qty_consumed": flt(c_line.qty),
								"packaging_summary": pack_summary,
								"packaging_cost": pack_total,
								"fg_item_code": fg2.item_code,
								"fg_item_name": fg2.item_name,
								"fg_batch_no": fg2.batch_no or "",
								"fg_qty_produced": flt(fg2.qty),
								"fg_uom": fg2.stock_uom,
								"fg_rate": flt(fg2.basic_rate),
								"fg_value": flt(fg2.amount),
								"fg_current_stock": fg2_stock
							})

		report_summary = self.build_summary_cards(tot_loose_qty, tot_rm_val, tot_fg_qty, tot_fg_val, tot_pack_val, 0)
		chart = self.build_chart(tot_rm_val, tot_pack_val, tot_fg_val)
		return data, report_summary, chart

	def build_reconciliation_summary(self, stage1_entries, stage2_entries):
		data = []
		reconcile = {}

		for se1 in stage1_entries:
			rm_cost = sum(flt(rm.amount) for rm in se1["consumed_items"])
			for fg1 in se1["finished_items"]:
				code = fg1.item_code
				if code not in reconcile:
					reconcile[code] = {
						"item_code": code,
						"item_name": fg1.item_name,
						"uom": fg1.stock_uom,
						"produced_qty": 0.0,
						"rm_cost": 0.0,
						"consumed_qty": 0.0,
						"packaging_cost": 0.0,
						"fg_units": 0.0,
						"fg_val": 0.0,
					}
				reconcile[code]["produced_qty"] += flt(fg1.qty)
				reconcile[code]["rm_cost"] += rm_cost

		for se2 in stage2_entries:
			pack_cost = sum(flt(p.amount) for p in se2["consumed_items"] if p.item_code not in self.loose_item_codes)
			fg_qty = sum(flt(f.qty) for f in se2["finished_items"])
			fg_amount = sum(flt(f.amount) for f in se2["finished_items"])

			for c in se2["consumed_items"]:
				code = c.item_code
				if code in reconcile:
					reconcile[code]["consumed_qty"] += flt(c.qty)
					reconcile[code]["packaging_cost"] += pack_cost
					reconcile[code]["fg_units"] += fg_qty
					reconcile[code]["fg_val"] += fg_amount

		tot_loose_qty = 0.0
		tot_rm_val = 0.0
		tot_fg_qty = 0.0
		tot_fg_val = 0.0
		tot_pack_val = 0.0
		tot_current_stock = 0.0

		for code, rec in reconcile.items():
			produced = rec["produced_qty"]
			consumed = rec["consumed_qty"]
			unconverted = produced - consumed
			avg_cost = (rec["rm_cost"] / produced) if produced > 0 else 0.0

			curr_stock = sum(qty for (item, wh), qty in self.bin_stock.items() if item == code)
			variance = unconverted - curr_stock

			tot_loose_qty += produced
			tot_rm_val += rec["rm_cost"]
			tot_fg_qty += rec["fg_units"]
			tot_fg_val += rec["fg_val"]
			tot_pack_val += rec["packaging_cost"]
			tot_current_stock += curr_stock

			data.append({
				"loose_item_code": code,
				"loose_item_name": rec["item_name"],
				"uom": rec["uom"],
				"total_produced_qty": round(produced, 3),
				"total_rm_cost": round(rec["rm_cost"], 2),
				"avg_rm_cost": round(avg_cost, 2),
				"total_consumed_qty": round(consumed, 3),
				"total_packaging_cost": round(rec["packaging_cost"], 2),
				"total_fg_units": round(rec["fg_units"], 2),
				"total_fg_val": round(rec["fg_val"], 2),
				"unconverted_qty": round(unconverted, 3),
				"current_wh_stock": round(curr_stock, 3),
				"stock_discrepancy": round(variance, 3)
			})

		report_summary = self.build_summary_cards(tot_loose_qty, tot_rm_val, tot_fg_qty, tot_fg_val, tot_pack_val, tot_current_stock)
		chart = self.build_chart(tot_rm_val, tot_pack_val, tot_fg_val)
		return data, report_summary, chart

	def build_summary_cards(self, loose_qty, rm_val, fg_qty, fg_val, pack_val, loose_stock):
		currency = frappe.defaults.get_user_default("currency") or "INR"
		return [
			{"value": loose_qty, "indicator": "Blue", "label": _("Total Bulk / Loose Produced"), "datatype": "Float"},
			{"value": rm_val, "indicator": "Orange", "label": _("Total RM Consumed Cost"), "datatype": "Currency", "currency": currency},
			{"value": fg_qty, "indicator": "Green", "label": _("Total FG Units Produced"), "datatype": "Float"},
			{"value": fg_val, "indicator": "Purple", "label": _("Total FG Valuation"), "datatype": "Currency", "currency": currency},
			{"value": pack_val, "indicator": "Gray", "label": _("Total Packaging Cost Added"), "datatype": "Currency", "currency": currency},
			{"value": loose_stock, "indicator": "Teal", "label": _("Current Loose Stock in Hand"), "datatype": "Float"},
		]

	def build_chart(self, rm_val, pack_val, fg_val):
		return {
			"data": {
				"labels": [_("RM Consumed Cost"), _("Packaging Cost Added"), _("Net FG Produced Value")],
				"datasets": [
					{
						"name": _("Cost & Valuation Breakdown"),
						"values": [round(rm_val, 2), round(pack_val, 2), round(fg_val, 2)]
					}
				]
			},
			"type": "bar",
			"colors": ["#f59e0b", "#8b5cf6", "#10b981"]
		}
