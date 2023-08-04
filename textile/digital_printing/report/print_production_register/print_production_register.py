# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _, scrub, unscrub
from frappe.utils import cint, cstr, flt, getdate
from frappe.desk.query_report import group_report_data


def execute(filters=None):
	return PrintProductionRegister(filters).run()


class PrintProductionRegister:
	def __init__(self, filters=None):
		self.filters = frappe._dict(filters or {})
		self.filters.from_date = getdate(filters.from_date)
		self.filters.to_date = getdate(filters.to_date)

		if self.filters.from_date > self.filters.to_date:
			frappe.throw(_("Date Range is incorrect"))

		self.show_item_name = frappe.defaults.get_global_default('item_naming_by') != "Item Name"
		self.show_customer_name = frappe.defaults.get_global_default('cust_master_name') == "Naming Series"

	def run(self):
		self.get_data()
		self.prepare_data()
		self.data = self.get_grouped_data()
		self.get_columns()

		return self.columns, self.data

	def get_data(self):
		conditions = self.get_conditions()

		self.data = frappe.db.sql("""
			SELECT se.name as stock_entry, se.posting_date, se.posting_time,
			    se.work_order, se.fabric_printer, se.fg_completed_qty as qty,
			    wo.print_order, wo.stock_uom as uom,
			    wo.customer, wo.customer_name,
			    wo.production_item as design_item, wo.item_name as design_item_name,
			    wo.process_item, wo.process_item_name,
			    wo.fabric_item, wo.fabric_item_name
			FROM `tabStock Entry` se
			INNER JOIN `tabWork Order` wo
				ON wo.name = se.work_order
			LEFT JOIN `tabItem` item
				ON item.name = wo.fabric_item
			WHERE se.docstatus = 1
				AND se.posting_date between %(from_date)s AND %(to_date)s
				{conditions}
			ORDER BY se.posting_date, se.posting_time, se.fabric_printer
		""".format(conditions=conditions), self.filters, as_dict=1)

	def get_conditions(self):
		conditions = []

		if self.filters.company:
			conditions.append("se.company = %(company)s")

		if self.filters.customer:
			conditions.append("wo.customer = %(customer)s")

		if self.filters.fabric_item:
			conditions.append("wo.fabric_item = %(fabric_item)s")

		if self.filters.fabric_material:
			conditions.append("item.fabric_material = %(fabric_material)s")

		if self.filters.fabric_type:
			conditions.append("item.fabric_type = %(fabric_type)s")

		if self.filters.print_order:
			if isinstance(self.filters.print_order, str):
				self.filters.print_order = cstr(self.filters.print_order).strip()
				self.filters.print_order = [d.strip() for d in self.filters.print_order.split(',') if d]

			conditions.append("wo.print_order in %(print_order)s")

		if self.filters.process_item:
			conditions.append("wo.process_item = %(process_item)s")

		if self.filters.fabric_printer:
			conditions.append("se.fabric_printer = %(fabric_printer)s")

		return "AND {}".format(" AND ".join(conditions)) if conditions else ""

	def prepare_data(self):
		for d in self.data:
			d["disable_item_formatter"] = 1

			d["reference_type"] = "Stock Entry"
			d["reference"] = d.stock_entry

	def get_grouped_data(self):
		data = self.data

		self.group_by = [None]
		for i in range(3):
			group_label = self.filters.get("group_by_" + str(i + 1), "").replace("Group by ", "")

			if group_label:
				self.group_by.append(scrub(group_label))

		if len(self.group_by) <= 1:
			return data

		return group_report_data(data, self.group_by, calculate_totals=self.calculate_group_totals,
			totals_only=self.filters.totals_only)

	def calculate_group_totals(self, data, group_field, group_value, grouped_by):
		totals = frappe._dict()

		# Copy grouped by into total row
		for f, g in grouped_by.items():
			totals[f] = g

		# Sum
		sum_fields = ['qty']
		for f in sum_fields:
			totals[f] = sum([flt(d.get(f)) for d in data])

		group_reference_doctypes = {
			"process_item": "Item",
			"fabric_item": "Item",
		}

		# set reference field
		reference_field = group_field[0] if isinstance(group_field, (list, tuple)) else group_field
		reference_dt = group_reference_doctypes.get(reference_field, unscrub(cstr(reference_field)))

		totals['reference_type'] = reference_dt
		if not group_field:
			totals['reference'] = "'Total'"
		elif not reference_dt:
			totals['reference'] = "'{0}'".format(grouped_by.get(reference_field))
		else:
			totals['reference'] = grouped_by.get(reference_field)

		if not group_field and self.group_by == [None]:
			totals['reference'] = "'Total'"

		# set item_code from model
		if "item_code" in grouped_by:
			totals['original_item_code'] = totals['item_code']
		elif "variant_of" in grouped_by:
			totals['item_code'] = totals['variant_of']
			totals['original_item_code'] = totals['variant_of']

		totals['disable_item_formatter'] = cint(self.show_item_name)

		if totals.get('fabric_item'):
			totals['fabric_item_name'] = data[0].fabric_item_name

		if totals.get('process_item'):
			totals['process_item_name'] = data[0].process_item_name

		if totals.get('customer'):
			totals['customer_name'] = data[0].customer_name

		return totals

	def get_columns(self):
		columns = [
			{
				"label": _("Date"),
				"fieldname": "posting_date",
				"fieldtype": "Date",
				"width": 85
			},
			{
				"label": _("Time"),
				"fieldname": "posting_time",
				"fieldtype": "Time",
				"width": 85
			},
			{
				"label": _("Print Order"),
				"fieldname": "print_order",
				"fieldtype": "Link",
				"options": "Print Order",
				"width": 100
			},
			{
				"label": _("Work Order"),
				"fieldname": "work_order",
				"fieldtype": "Link",
				"options": "Work Order",
				"width": 100
			},
			{
				"label": _("Stock Entry"),
				"fieldname": "stock_entry",
				"fieldtype": "Link",
				"options": "Stock Entry",
				"width": 120
			},
			{
				"label": _("Printer"),
				"fieldname": "fabric_printer",
				"fieldtype": "Link",
				"options": "Fabric Printer",
				"width": 80
			},
			{
				"label": _("Process"),
				"fieldname": "process_item_name",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"label": _("Customer"),
				"fieldname": "customer",
				"fieldtype": "Link",
				"options": "Customer",
				"width": 80 if self.show_customer_name else 150
			},
			{
				"label": _("Customer Name"),
				"fieldname": "customer_name",
				"fieldtype": "Data",
				"width": 150
			},
			{
				"label": _("Fabric Item"),
				"fieldname": "fabric_item",
				"fieldtype": "Link",
				"options": "Item",
				"width": 100 if self.show_item_name else 150
			},
			{
				"label": _("Fabric Name"),
				"fieldname": "fabric_item_name",
				"fieldtype": "Data",
				"width": 160
			},
			{
				"label": _("Design Item"),
				"fieldname": "design_item",
				"fieldtype": "Link",
				"options": "Item",
				"width": 100 if self.show_item_name else 150
			},
			{
				"label": _("Design Name"),
				"fieldname": "design_item_name",
				"fieldtype": "Data",
				"width": 160
			},
			{
				"label": _("Qty"),
				"fieldname": "qty",
				"fieldtype": "Float",
				"width": 80
			},
			{
				"label": _("UOM"),
				"fieldname": "uom",
				"fieldtype": "Link",
				"options": "UOM",
				"width": 60
			},
		]

		if not self.show_customer_name:
			columns = [c for c in columns if c['fieldname'] != 'customer_name']

		if not self.show_item_name:
			columns = [c for c in columns if c['fieldname'] != ['fabric_item_name', 'design_item_name', 'process_item_name']]

		if len(self.group_by) > 1:
			columns = [c for c in columns if c['fieldname'] != 'stock_entry']

			reference_column = {
				"label": _("Reference"),
				"fieldname": "reference",
				"fieldtype": "Dynamic Link",
				"options": "reference_type",
				"width": 200
			}

			columns.insert(0, reference_column)

		self.columns = columns
