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
		{"fieldname": "journey", "label": _("Journey / Stage"), "fieldtype": "Data", "width": 320},
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
		self.item_meta = {}
		self.load_initial_metadata()

	def load_initial_metadata(self):
		for u in frappe.db.sql("SELECT name, full_name FROM `tabUser`", as_dict=True):
			self.users[u.name] = u.full_name or u.name

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

		bins = frappe.db.sql("""
			SELECT item_code, warehouse, actual_qty, stock_value
			FROM `tabBin`
			WHERE item_code IN %(item_codes)s
		""", {"item_codes": list(item_codes)}, as_dict=True)
		for b in bins:
			self.bin_stock[(b.item_code, b.warehouse)] = flt(b.actual_qty)

		items = frappe.db.sql("""
			SELECT item_code, item_name, stock_uom
			FROM `tabItem`
			WHERE item_code IN %(item_codes)s
		""", {"item_codes": list(item_codes)}, as_dict=True)
		for it in items:
			self.item_meta[it.item_code] = it

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

		# Explicit, strict resolution of target loose items
		target_loose_items = set()
		if self.filters.get("loose_item_code"):
			target_loose_items.add(self.filters.loose_item_code)
		elif self.filters.get("fg_item_code"):
			fg_code = self.filters.fg_item_code
			for se in se_grouped.values():
				if any(f.item_code == fg_code for f in se["finished_items"]):
					for c in se["consumed_items"]:
						if c.item_code in self.loose_item_codes:
							target_loose_items.add(c.item_code)
		elif self.filters.get("rm_item_code"):
			rm_code = self.filters.rm_item_code
			for se in se_grouped.values():
				if any(c.item_code == rm_code for c in se["consumed_items"]):
					for f in se["finished_items"]:
						if f.item_code in self.loose_item_codes:
							target_loose_items.add(f.item_code)
		else:
			target_loose_items = set(self.loose_item_codes)

		stage1_entries = []
		stage2_entries = []
		seen_se1 = set()
		seen_se2 = set()

		for se_no, se in se_grouped.items():
			# Check Stage 1: Produces an item in target_loose_items
			is_s1 = any(f.item_code in target_loose_items for f in se["finished_items"])
			if is_s1 and se_no not in seen_se1:
				if not self.filters.get("rm_item_code") or any(c.item_code == self.filters.rm_item_code for c in se["consumed_items"]):
					stage1_entries.append(se)
					seen_se1.add(se_no)

			# Check Stage 2: Consumes an item in target_loose_items
			is_s2 = any(c.item_code in target_loose_items for c in se["consumed_items"])
			if is_s2 and se_no not in seen_se2:
				if not self.filters.get("fg_item_code") or any(f.item_code == self.filters.fg_item_code for f in se["finished_items"]):
					stage2_entries.append(se)
					seen_se2.add(se_no)

		if self.filters.get("batch_no"):
			b_filter = self.filters.batch_no
			stage1_entries = [se for se in stage1_entries if any(f.batch_no == b_filter for f in se["finished_items"]) or any(c.batch_no == b_filter for c in se["consumed_items"])]
			stage2_entries = [se for se in stage2_entries if any(f.batch_no == b_filter for f in se["finished_items"]) or any(c.batch_no == b_filter for c in se["consumed_items"])]

		return stage1_entries, stage2_entries, target_loose_items

	def run(self, view_mode="Hierarchical Journey Tree"):
		stage1_entries, stage2_entries, target_loose_items = self.fetch_production_entries()

		all_items = set(target_loose_items)
		all_batches = set()
		for se in stage1_entries + stage2_entries:
			for item in se["finished_items"] + se["consumed_items"]:
				if item.item_code:
					all_items.add(item.item_code)
				if item.batch_no:
					all_batches.add(item.batch_no)

		self.load_item_batch_stock(all_items, all_batches)
		
		report_summary, chart = self.compute_exact_metrics(stage1_entries, stage2_entries, target_loose_items)

		if view_mode == "Batch Lineage Matrix":
			data = self.build_lineage_matrix(stage1_entries, stage2_entries, target_loose_items)
		elif view_mode == "Loose Item Reconciliation Summary":
			data = self.build_reconciliation_summary(stage1_entries, stage2_entries, target_loose_items)
		else:
			data = self.build_journey_tree(stage1_entries, stage2_entries, target_loose_items)

		return data, report_summary, chart

	def compute_exact_metrics(self, stage1_entries, stage2_entries, target_loose_items):
		tot_loose_qty = 0.0
		tot_rm_val = 0.0
		loose_stock_set = set()

		for se in stage1_entries:
			for f in se["finished_items"]:
				if f.item_code in target_loose_items:
					tot_loose_qty += flt(f.qty)
					loose_stock_set.add((f.item_code, f.t_warehouse))
			for c in se["consumed_items"]:
				if not self.filters.get("rm_item_code") or c.item_code == self.filters.rm_item_code:
					tot_rm_val += flt(c.amount)

		tot_fg_qty = 0.0
		tot_fg_val = 0.0
		tot_pack_val = 0.0
		for se in stage2_entries:
			for f in se["finished_items"]:
				if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code:
					tot_fg_qty += flt(f.qty)
					tot_fg_val += flt(f.amount)
			for c in se["consumed_items"]:
				if c.item_code not in self.loose_item_codes:
					tot_pack_val += flt(c.amount)

		current_loose_stock = sum(self.bin_stock.get(key, 0.0) for key in loose_stock_set) if loose_stock_set else sum(qty for (it, wh), qty in self.bin_stock.items() if it in target_loose_items)

		currency = frappe.defaults.get_user_default("currency") or "INR"
		summary = [
			{"value": tot_loose_qty, "indicator": "Blue", "label": _("Total Bulk / Loose Produced"), "datatype": "Float"},
			{"value": tot_rm_val, "indicator": "Orange", "label": _("Total RM Consumed Cost"), "datatype": "Currency", "currency": currency},
			{"value": tot_fg_qty, "indicator": "Green", "label": _("Total FG Units Produced"), "datatype": "Float"},
			{"value": tot_fg_val, "indicator": "Purple", "label": _("Total FG Valuation"), "datatype": "Currency", "currency": currency},
			{"value": tot_pack_val, "indicator": "Gray", "label": _("Total Packaging Cost Added"), "datatype": "Currency", "currency": currency},
			{"value": current_loose_stock, "indicator": "Teal", "label": _("Current Loose Stock in Hand"), "datatype": "Float"},
		]

		chart = {
			"data": {
				"labels": [_("RM Consumed Cost"), _("Packaging Cost Added"), _("Net FG Produced Value")],
				"datasets": [
					{
						"name": _("Cost & Valuation Breakdown"),
						"values": [round(tot_rm_val, 2), round(tot_pack_val, 2), round(tot_fg_val, 2)]
					}
				]
			},
			"type": "bar",
			"colors": ["#f59e0b", "#8b5cf6", "#10b981"]
		}
		return summary, chart

	def build_journey_tree(self, stage1_entries, stage2_entries, target_loose_items):
		data = []

		for l_code in sorted(target_loose_items):
			se1_for_loose = [se for se in stage1_entries if any(f.item_code == l_code for f in se["finished_items"])]
			se2_for_loose = [se for se in stage2_entries if any(c.item_code == l_code for c in se["consumed_items"])]

			if not se1_for_loose and not se2_for_loose:
				continue

			l_meta = self.item_meta.get(l_code)
			l_name = l_meta.item_name if l_meta else l_code
			l_uom = l_meta.stock_uom if l_meta else ""
			wh_stock = sum(qty for (it, wh), qty in self.bin_stock.items() if it == l_code)

			total_s1_qty = sum(flt(f.qty) for se in se1_for_loose for f in se["finished_items"] if f.item_code == l_code)
			total_s1_cost = sum(flt(c.amount) for se in se1_for_loose for c in se["consumed_items"])
			total_s2_consumed = sum(flt(c.qty) for se in se2_for_loose for c in se["consumed_items"] if c.item_code == l_code)
			total_s2_fg_qty = sum(flt(f.qty) for se in se2_for_loose for f in se["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code)
			total_s2_fg_val = sum(flt(f.amount) for se in se2_for_loose for f in se["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code)

			# Node 0: Loose Item Overview Node
			data.append({
				"journey": f"🏷️ [Loose Item] {l_name} ({l_code})",
				"item_code": l_code,
				"item_name": l_name,
				"uom": l_uom,
				"qty": total_s1_qty,
				"current_wh_qty": wh_stock,
				"stage_type": "Loose Item Header",
				"created_by": f"Stock: {wh_stock} {l_uom}",
				"indent": 0
			})

			# Node 1: Stage 1 Section Header
			if se1_for_loose:
				data.append({
					"journey": f"🔵 [Stage 1: Bulk Production] {len(se1_for_loose)} Entries | Produced: {total_s1_qty:,.2f} {l_uom} | RM Cost: ₹{total_s1_cost:,.2f}",
					"item_code": l_code,
					"item_name": l_name,
					"uom": l_uom,
					"qty": total_s1_qty,
					"amount": total_s1_cost,
					"stage_type": "Stage 1 Section",
					"indent": 1
				})

				for se1 in se1_for_loose:
					se1_user = self.users.get(se1["owner"], se1["owner"])
					fg1 = next((f for f in se1["finished_items"] if f.item_code == l_code), None)
					if not fg1:
						continue

					batch_no = fg1.batch_no or ""
					wh = fg1.t_warehouse or ""
					b_info = self.batches.get(batch_no, {})
					wh_stock_entry = self.bin_stock.get((l_code, wh), 0.0)
					b_stock = self.batch_stock.get((l_code, wh, batch_no), 0.0) if batch_no else wh_stock_entry

					b_label = f" [B#{batch_no}]" if batch_no else ""
					data.append({
						"journey": f"🔵 [Stage 1 SE] {se1['se_no']}{b_label}",
						"posting_date": se1["posting_date"],
						"voucher_type": "Stock Entry",
						"voucher_no": se1["se_no"],
						"bom_no": se1["bom_no"],
						"item_code": l_code,
						"item_name": fg1.item_name or l_name,
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
						"current_wh_qty": wh_stock_entry,
						"created_by": se1_user,
						"indent": 2
					})

					for rm in se1["consumed_items"]:
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
							"created_by": se1_user,
							"indent": 3
						})

			# Node 1: Stage 2 Section Header
			if se2_for_loose:
				data.append({
					"journey": f"🟢 [Stage 2: Packaging Runs] {len(se2_for_loose)} Entries | Packaged: {total_s2_consumed:,.2f} {l_uom} ➔ {total_s2_fg_qty:,.2f} FG Units | Valuation: ₹{total_s2_fg_val:,.2f}",
					"item_code": l_code,
					"item_name": l_name,
					"uom": "Units",
					"qty": total_s2_fg_qty,
					"amount": total_s2_fg_val,
					"stage_type": "Stage 2 Section",
					"indent": 1
				})

				for se2 in se2_for_loose:
					se2_user = self.users.get(se2["owner"], se2["owner"])

					fg_list = [f for f in se2["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code]
					fg_desc = ", ".join(f"{f.item_name or f.item_code} ({flt(f.qty)} {f.stock_uom})" for f in fg_list)

					data.append({
						"journey": f"🟢 [Stage 2 SE] {se2['se_no']}",
						"posting_date": se2["posting_date"],
						"voucher_type": "Stock Entry",
						"voucher_no": se2["se_no"],
						"bom_no": se2["bom_no"],
						"item_code": fg_list[0].item_code if fg_list else "",
						"item_name": fg_desc,
						"stage_type": "FG Produced",
						"qty": sum(flt(f.qty) for f in fg_list),
						"amount": sum(flt(f.amount) for f in fg_list),
						"created_by": se2_user,
						"indent": 2
					})

					# Loose Item Consumed
					c_loose = next((c for c in se2["consumed_items"] if c.item_code == l_code), None)
					if c_loose:
						c_batch = c_loose.batch_no or ""
						c_wh = c_loose.s_warehouse or ""
						c_b_info = self.batches.get(c_batch, {})
						c_wh_stock = self.bin_stock.get((l_code, c_wh), 0.0)
						c_b_stock = self.batch_stock.get((l_code, c_wh, c_batch), 0.0) if c_batch else c_wh_stock
						c_batch_str = f" [B#{c_batch}]" if c_batch else ""

						data.append({
							"journey": f"  ↳ 🔵 [Loose Consumed] {c_loose.item_name or l_code}{c_batch_str}",
							"posting_date": se2["posting_date"],
							"voucher_type": "Stock Entry",
							"voucher_no": se2["se_no"],
							"bom_no": se2["bom_no"],
							"item_code": l_code,
							"item_name": c_loose.item_name or l_name,
							"batch_no": c_batch,
							"mfg_date": c_b_info.get("manufacturing_date"),
							"expiry_date": c_b_info.get("expiry_date"),
							"stage_type": "Loose Consumed",
							"qty": flt(c_loose.qty),
							"uom": c_loose.stock_uom,
							"basic_rate": flt(c_loose.basic_rate),
							"amount": flt(c_loose.amount),
							"warehouse": c_wh,
							"current_batch_qty": c_b_stock,
							"current_wh_qty": c_wh_stock,
							"created_by": se2_user,
							"indent": 3
						})

					# Packaging Materials Consumed
					for p_item in se2["consumed_items"]:
						if p_item.item_code == l_code:
							continue
						p_batch = p_item.batch_no or ""
						p_wh = p_item.s_warehouse or ""
						p_b_info = self.batches.get(p_batch, {})
						p_wh_stock = self.bin_stock.get((p_item.item_code, p_wh), 0.0)
						p_b_stock = self.batch_stock.get((p_item.item_code, p_wh, p_batch), 0.0) if p_batch else p_wh_stock
						p_batch_str = f" [B#{p_batch}]" if p_batch else ""

						data.append({
							"journey": f"  ↳ 🟣 [Packaging] {p_item.item_name or p_item.item_code}{p_batch_str}",
							"posting_date": se2["posting_date"],
							"voucher_type": "Stock Entry",
							"voucher_no": se2["se_no"],
							"bom_no": se2["bom_no"],
							"item_code": p_item.item_code,
							"item_name": p_item.item_name,
							"batch_no": p_batch,
							"mfg_date": p_b_info.get("manufacturing_date"),
							"expiry_date": p_b_info.get("expiry_date"),
							"stage_type": "Packaging Consumed",
							"qty": flt(p_item.qty),
							"uom": p_item.stock_uom,
							"basic_rate": flt(p_item.basic_rate),
							"amount": flt(p_item.amount),
							"warehouse": p_wh,
							"current_batch_qty": p_b_stock,
							"current_wh_qty": p_wh_stock,
							"created_by": se2_user,
							"indent": 3
						})

					# Finished Goods Produced
					for fg in fg_list:
						fg_batch = fg.batch_no or ""
						fg_wh = fg.t_warehouse or ""
						fg_b_info = self.batches.get(fg_batch, {})
						fg_wh_stock = self.bin_stock.get((fg.item_code, fg_wh), 0.0)
						fg_b_stock = self.batch_stock.get((fg.item_code, fg_wh, fg_batch), 0.0) if fg_batch else fg_wh_stock
						fg_batch_str = f" [B#{fg_batch}]" if fg_batch else ""

						data.append({
							"journey": f"  ↳ ✨ [FG Produced] {fg.item_name or fg.item_code}{fg_batch_str}",
							"posting_date": se2["posting_date"],
							"voucher_type": "Stock Entry",
							"voucher_no": se2["se_no"],
							"bom_no": se2["bom_no"],
							"item_code": fg.item_code,
							"item_name": fg.item_name,
							"batch_no": fg_batch,
							"mfg_date": fg_b_info.get("manufacturing_date"),
							"expiry_date": fg_b_info.get("expiry_date"),
							"stage_type": "FG Produced",
							"qty": flt(fg.qty),
							"uom": fg.stock_uom,
							"basic_rate": flt(fg.basic_rate),
							"amount": flt(fg.amount),
							"warehouse": fg_wh,
							"current_batch_qty": fg_b_stock,
							"current_wh_qty": fg_wh_stock,
							"created_by": se2_user,
							"indent": 3
						})

		return data

	def build_lineage_matrix(self, stage1_entries, stage2_entries, target_loose_items):
		data = []

		for l_code in sorted(target_loose_items):
			se1_for_loose = [se for se in stage1_entries if any(f.item_code == l_code for f in se["finished_items"])]
			se2_for_loose = [se for se in stage2_entries if any(c.item_code == l_code for c in se["consumed_items"])]

			l_meta = self.item_meta.get(l_code)
			l_name = l_meta.item_name if l_meta else l_code
			wh_stock = sum(qty for (it, wh), qty in self.bin_stock.items() if it == l_code)

			s1_rows = []
			for se1 in se1_for_loose:
				se1_user = self.users.get(se1["owner"], se1["owner"])
				fg1 = next((f for f in se1["finished_items"] if f.item_code == l_code), None)
				if not fg1:
					continue
				rm_parts = [f"{rm.item_code}: {rm.qty} {rm.stock_uom}" for rm in se1["consumed_items"]]
				rm_total = sum(flt(rm.amount) for rm in se1["consumed_items"])

				s1_rows.append({
					"stage1_se": se1["se_no"],
					"stage1_date": se1["posting_date"],
					"stage1_user": se1_user,
					"rm_summary": ", ".join(rm_parts),
					"rm_cost": rm_total,
					"loose_item_code": l_code,
					"loose_item_name": fg1.item_name or l_name,
					"loose_batch_no": fg1.batch_no or "",
					"loose_qty_produced": flt(fg1.qty),
					"loose_uom": fg1.stock_uom,
					"loose_rate": flt(fg1.basic_rate),
					"loose_val": flt(fg1.amount),
					"loose_current_stock": wh_stock,
				})

			s2_rows = []
			for se2 in se2_for_loose:
				se2_user = self.users.get(se2["owner"], se2["owner"])
				c_loose = next((c for c in se2["consumed_items"] if c.item_code == l_code), None)
				loose_qty = flt(c_loose.qty) if c_loose else 0.0

				pack_parts = [f"{p.item_name or p.item_code}: {p.qty}" for p in se2["consumed_items"] if p.item_code != l_code]
				pack_total = sum(flt(p.amount) for p in se2["consumed_items"] if p.item_code != l_code)

				fg_list = [f for f in se2["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code]
				for fg in fg_list:
					fg_wh = fg.t_warehouse or ""
					fg_stock = self.bin_stock.get((fg.item_code, fg_wh), 0.0)

					s2_rows.append({
						"stage2_se": se2["se_no"],
						"stage2_date": se2["posting_date"],
						"stage2_user": se2_user,
						"stage2_bom": se2["bom_no"],
						"loose_qty_consumed": loose_qty,
						"packaging_summary": ", ".join(pack_parts),
						"packaging_cost": pack_total,
						"fg_item_code": fg.item_code,
						"fg_item_name": fg.item_name,
						"fg_batch_no": fg.batch_no or "",
						"fg_qty_produced": flt(fg.qty),
						"fg_uom": fg.stock_uom,
						"fg_rate": flt(fg.basic_rate),
						"fg_value": flt(fg.amount),
						"fg_current_stock": fg_stock
					})

			max_len = max(len(s1_rows), len(s2_rows))
			for i in range(max_len):
				r1 = s1_rows[i] if i < len(s1_rows) else {
					"stage1_se": "", "stage1_date": None, "stage1_user": "", "rm_summary": "-", "rm_cost": 0.0,
					"loose_item_code": l_code, "loose_item_name": l_name, "loose_batch_no": "",
					"loose_qty_produced": 0.0, "loose_uom": "", "loose_rate": 0.0, "loose_val": 0.0, "loose_current_stock": wh_stock
				}
				r2 = s2_rows[i] if i < len(s2_rows) else {
					"stage2_se": "", "stage2_date": None, "stage2_user": "", "stage2_bom": "", "loose_qty_consumed": 0.0,
					"packaging_summary": "-", "packaging_cost": 0.0, "fg_item_code": "-", "fg_item_name": "Unpackaged / In Stock",
					"fg_batch_no": "", "fg_qty_produced": 0.0, "fg_uom": "", "fg_rate": 0.0, "fg_value": 0.0, "fg_current_stock": 0.0
				}
				merged = dict(r1)
				merged.update(r2)
				data.append(merged)

		return data

	def build_reconciliation_summary(self, stage1_entries, stage2_entries, target_loose_items):
		data = []

		for l_code in sorted(target_loose_items):
			se1_for_loose = [se for se in stage1_entries if any(f.item_code == l_code for f in se["finished_items"])]
			se2_for_loose = [se for se in stage2_entries if any(c.item_code == l_code for c in se["consumed_items"])]

			if not se1_for_loose and not se2_for_loose:
				continue

			l_meta = self.item_meta.get(l_code)
			l_name = l_meta.item_name if l_meta else l_code
			l_uom = l_meta.stock_uom if l_meta else ""
			wh_stock = sum(qty for (it, wh), qty in self.bin_stock.items() if it == l_code)

			produced_qty = sum(flt(f.qty) for se in se1_for_loose for f in se["finished_items"] if f.item_code == l_code)
			rm_cost = sum(flt(c.amount) for se in se1_for_loose for c in se["consumed_items"])
			avg_cost = (rm_cost / produced_qty) if produced_qty > 0 else 0.0

			consumed_qty = sum(flt(c.qty) for se in se2_for_loose for c in se["consumed_items"] if c.item_code == l_code)
			pack_cost = sum(flt(p.amount) for se in se2_for_loose for p in se["consumed_items"] if p.item_code not in self.loose_item_codes)
			fg_units = sum(flt(f.qty) for se in se2_for_loose for f in se["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code)
			fg_val = sum(flt(f.amount) for se in se2_for_loose for f in se["finished_items"] if not self.filters.get("fg_item_code") or f.item_code == self.filters.fg_item_code)

			unconverted = produced_qty - consumed_qty
			variance = unconverted - wh_stock

			data.append({
				"loose_item_code": l_code,
				"loose_item_name": l_name,
				"uom": l_uom,
				"total_produced_qty": round(produced_qty, 3),
				"total_rm_cost": round(rm_cost, 2),
				"avg_rm_cost": round(avg_cost, 2),
				"total_consumed_qty": round(consumed_qty, 3),
				"total_packaging_cost": round(pack_cost, 2),
				"total_fg_units": round(fg_units, 2),
				"total_fg_val": round(fg_val, 2),
				"unconverted_qty": round(unconverted, 3),
				"current_wh_stock": round(wh_stock, 3),
				"stock_discrepancy": round(variance, 3)
			})

		return data
