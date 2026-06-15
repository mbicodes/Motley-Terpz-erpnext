import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, nowtime, getdate

class ManufactureStockEntry(Document):
    def validate(self):
        self.validate_quantities()
        self.validate_batch_availability()
        self.set_missing_values()
        if self.date and getdate(self.date) > getdate(nowdate()):
            frappe.throw(_("The date cannot be in the future."))
        self.actual_qty_sum = sum(row.qty for row in self.manufacture_raw_material)
        self.bom_qty_sum = sum(row.qty for row in self.manufacture_finished_goods)
        self.diff_qty_sum = self.actual_qty_sum - self.bom_qty_sum

    def validate_quantities(self):
        for item in self.get("manufacture_raw_material", []):
            if flt(item.qty) <= 0:
                frappe.throw(_("Row #{0}: Quantity must be greater than 0").format(item.idx))
                
        for item in self.get("manufacture_finished_goods", []):
            if flt(item.qty) <= 0:
                frappe.throw(_("Row #{0}: Quantity must be greater than 0").format(item.idx))
    
    def validate_batch_availability(self):
        """Validate that batch quantities are sufficient for raw materials"""
        for item in self.get("manufacture_raw_material", []):
            if item.batch_no:
                batch_qty = frappe.db.get_value("Batch", item.batch_no, "batch_qty")
                if batch_qty is not None and flt(item.qty) > flt(batch_qty):
                    frappe.throw(_(
                        "Row #{0}: Insufficient quantity in batch {1}. "
                        "Available: {2}, Required: {3}"
                    ).format(item.idx, item.batch_no, batch_qty, item.qty))
    
    def set_missing_values(self):
        if not self.date:
            self.date = nowdate()
        if not self.time:
            self.time = nowtime()
    
    def get_expense_accounts(self):
        """Fetch expense accounts from Stock Settings based on company and type"""
        accounts = frappe.get_all(
            "Manufacture Stock Setting",
            filters={"parent": "Stock Settings", "company": self.company},
            fields=["premix_account", "manufacturing_account", "packing_account", "finished_goods_account", "premix_finished_goods_account"],
            limit=1
        )
        
        if accounts:
            type_account_map = {
                "Premix": "premix_account",
                "Manufacturing": "manufacturing_account",
                "Packing": "packing_account"
            }
            
            account_field = type_account_map.get(self.type)
            raw_material_account = accounts[0].get(account_field) if account_field else None
            
            if self.type == "Premix":
                finished_goods_account = accounts[0].get("premix_finished_goods_account")
            else:
                finished_goods_account = accounts[0].get("finished_goods_account")
            
            return {
                "raw_material_account": raw_material_account,
                "finished_goods_account": finished_goods_account
            }
        
        return {"raw_material_account": None, "finished_goods_account": None}
    
    def before_save(self):
        pass

    def after_insert(self):
        """Runs after the document is saved to DB for the first time,
        so the name exists and links will validate correctly."""
        issue_se = self.create_material_issue()
        self.db_set("material_issue_ref", issue_se)

        receipt_se = self.create_material_receipt()
        self.db_set("material_receipt_ref", receipt_se)

    def on_update(self):
        """Runs on every subsequent save after the first."""
        if self.material_issue_ref:
            self.update_material_issue()
        else:
            issue_se = self.create_material_issue()
            self.db_set("material_issue_ref", issue_se)

        if self.material_receipt_ref:
            self.update_material_receipt()
        else:
            receipt_se = self.create_material_receipt()
            self.db_set("material_receipt_ref", receipt_se)

    def on_submit(self):
        # Submit both stock entries when parent document is submitted
        if self.material_issue_ref:
            issue_doc = frappe.get_doc("Stock Entry", self.material_issue_ref)
            if issue_doc.docstatus == 0:
                issue_doc.submit()
                
        if self.material_receipt_ref:
            receipt_doc = frappe.get_doc("Stock Entry", self.material_receipt_ref)
            if receipt_doc.docstatus == 0:
                # Get total_outgoing_value from Material Issue
                issue_doc = frappe.get_doc("Stock Entry", self.material_issue_ref)
                total_outgoing_value = flt(issue_doc.total_outgoing_value)
                
                # Distribute amount equally among finished goods items
                if receipt_doc.items:
                    num_items = len(receipt_doc.items)
                    amount_per_item = total_outgoing_value / num_items if num_items > 0 else 0
                    
                    for item in receipt_doc.items:
                        rate_per_unit = amount_per_item / flt(item.qty) if flt(item.qty) > 0 else 0
                        
                        frappe.db.sql("""
                            UPDATE `tabStock Entry Detail`
                            SET 
                                basic_rate = %s,
                                basic_amount = %s,
                                amount = %s,
                                valuation_rate = %s
                            WHERE name = %s
                        """, (rate_per_unit, amount_per_item, amount_per_item, rate_per_unit, item.name))
                    
                    frappe.db.sql("""
                        UPDATE `tabStock Entry`
                        SET 
                            total_incoming_value = %s,
                            value_difference = %s
                        WHERE name = %s
                    """, (total_outgoing_value, 0, receipt_doc.name))
                    
                    frappe.db.commit()
                    
                    frappe.log_error(f"Updated Material Receipt {receipt_doc.name} via SQL - Total: {total_outgoing_value}, Items: {num_items}, Per Item: {amount_per_item}")
                
                receipt_doc.reload()
                receipt_doc.submit()
	
    def create_material_issue(self):
        if not self.manufacture_raw_material:
            frappe.throw("No Raw Material found to create Material Issue")
        
        accounts = self.get_expense_accounts()
        
        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Issue",
            "company": self.company,
            "posting_date": self.date,
            "posting_time": self.time,
            "set_posting_time": 1,
            "custom_manufacture_stock_entry": self.name,
            "items": []
        })
        
        batch_items = []
        
        for idx, row in enumerate(self.manufacture_raw_material):
            if not row.qty or row.qty <= 0:
                continue
            
            item_dict = {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "s_warehouse": row.warehouse,
                "custom_bom_qty": flt(row.bom_qty),
            }
            
            if accounts.get("raw_material_account"):
                item_dict["expense_account"] = accounts.get("raw_material_account")
            
            if row.batch_no:
                batch_items.append({
                    'idx': idx,
                    'batch_no': row.batch_no,
                    'qty': flt(row.qty),
                    'warehouse': row.warehouse
                })
                
                try:
                    batch_doc = frappe.get_doc("Batch", row.batch_no)
                    if hasattr(batch_doc, 'manufacturing_date') and batch_doc.manufacturing_date:
                        item_dict["manufacturing_date"] = batch_doc.manufacturing_date
                    if hasattr(batch_doc, 'expiry_date') and batch_doc.expiry_date:
                        item_dict["expiry_date"] = batch_doc.expiry_date
                except:
                    pass
            else:
                has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")
                if has_batch_no:
                    item_dict["use_serial_batch_fields"] = 1
            
            se.append("items", item_dict)
        
        se.insert(ignore_permissions=True)
        
        for batch_item in batch_items:
            idx = batch_item['idx']
            if idx < len(se.items):
                se_item = se.items[idx]
                bundle_name = create_batch_bundle(
                    se_item, 
                    batch_item['batch_no'], 
                    batch_item['qty'], 
                    batch_item['warehouse'], 
                    "outward",
                    se.posting_date,
                    se.posting_time
                )
                
                if bundle_name:
                    frappe.db.set_value("Stock Entry Detail", se_item.name, {
                        "serial_and_batch_bundle": bundle_name,
                        "batch_no": batch_item['batch_no']
                    })
        
        frappe.db.commit()
        se.reload()
        return se.name
	
    def update_material_issue(self):
        if not self.material_issue_ref:
            return
        
        se = frappe.get_doc("Stock Entry", self.material_issue_ref)
        
        if se.docstatus != 0:
            frappe.throw("Cannot update submitted Stock Entry")
        
        accounts = self.get_expense_accounts()
        
        se.posting_date = self.date
        se.posting_time = self.time
        se.set_posting_time = 1
        
        for item in se.items:
            if hasattr(item, 'serial_and_batch_bundle') and item.serial_and_batch_bundle:
                if frappe.db.exists("Serial and Batch Bundle", item.serial_and_batch_bundle):
                    frappe.delete_doc("Serial and Batch Bundle", item.serial_and_batch_bundle, force=1, ignore_permissions=True)
        
        se.items = []
        
        batch_items = []
        
        for idx, row in enumerate(self.manufacture_raw_material):
            if not row.qty or row.qty <= 0:
                continue
            
            item_dict = {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "s_warehouse": row.warehouse,
                "custom_bom_qty": flt(row.bom_qty),
            }
            
            if accounts.get("raw_material_account"):
                item_dict["expense_account"] = accounts.get("raw_material_account")
            
            if row.batch_no:
                batch_items.append({
                    'idx': idx,
                    'batch_no': row.batch_no,
                    'qty': flt(row.qty),
                    'warehouse': row.warehouse
                })
                
                try:
                    batch_doc = frappe.get_doc("Batch", row.batch_no)
                    if hasattr(batch_doc, 'manufacturing_date') and batch_doc.manufacturing_date:
                        item_dict["manufacturing_date"] = batch_doc.manufacturing_date
                    if hasattr(batch_doc, 'expiry_date') and batch_doc.expiry_date:
                        item_dict["expiry_date"] = batch_doc.expiry_date
                except:
                    pass
            else:
                has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")
                if has_batch_no:
                    item_dict["use_serial_batch_fields"] = 1
            
            se.append("items", item_dict)
        
        se.save(ignore_permissions=True)
        
        for batch_item in batch_items:
            idx = batch_item['idx']
            if idx < len(se.items):
                se_item = se.items[idx]
                bundle_name = create_batch_bundle(
                    se_item, 
                    batch_item['batch_no'], 
                    batch_item['qty'], 
                    batch_item['warehouse'], 
                    "outward",
                    se.posting_date,
                    se.posting_time
                )
                
                if bundle_name:
                    frappe.db.set_value("Stock Entry Detail", se_item.name, {
                        "serial_and_batch_bundle": bundle_name,
                        "batch_no": batch_item['batch_no']
                    })
        
        frappe.db.commit()
        se.reload()
	
    def create_material_receipt(self):
        if not self.manufacture_finished_goods:
            frappe.throw("No Finished Goods found to create Material Receipt")
        
        accounts = self.get_expense_accounts()
        
        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "custom_manufacture_stock_entry": self.name,
            "posting_date": self.date,
            "posting_time": self.time,
            "set_posting_time": 1,
            "items": []
        })
        
        batch_items = []
        
        for idx, row in enumerate(self.manufacture_finished_goods):
            if not row.qty or row.qty <= 0:
                continue
            
            item_dict = {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "t_warehouse": row.warehouse,
                "custom_bom_qty": flt(row.bom_qty),
                "basic_rate": 1
            }
            
            if accounts.get("finished_goods_account"):
                item_dict["expense_account"] = accounts.get("finished_goods_account")
            
            if row.batch_no:
                batch_items.append({
                    'idx': idx,
                    'batch_no': row.batch_no,
                    'qty': flt(row.qty),
                    'warehouse': row.warehouse
                })
                
                try:
                    batch_doc = frappe.get_doc("Batch", row.batch_no)
                    if hasattr(batch_doc, 'manufacturing_date') and batch_doc.manufacturing_date:
                        item_dict["manufacturing_date"] = batch_doc.manufacturing_date
                    if hasattr(batch_doc, 'expiry_date') and batch_doc.expiry_date:
                        item_dict["expiry_date"] = batch_doc.expiry_date
                except:
                    pass
            else:
                has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")
                if has_batch_no:
                    item_dict["use_serial_batch_fields"] = 1
            
            se.append("items", item_dict)
        
        se.insert(ignore_permissions=True)
        
        for batch_item in batch_items:
            idx = batch_item['idx']
            if idx < len(se.items):
                se_item = se.items[idx]
                bundle_name = create_batch_bundle(
                    se_item, 
                    batch_item['batch_no'], 
                    batch_item['qty'], 
                    batch_item['warehouse'], 
                    "inward",
                    se.posting_date,
                    se.posting_time
                )
                
                if bundle_name:
                    frappe.db.set_value("Stock Entry Detail", se_item.name, {
                        "serial_and_batch_bundle": bundle_name,
                        "batch_no": batch_item['batch_no']
                    })
        
        frappe.db.commit()
        se.reload()
        return se.name
	
    def update_material_receipt(self):
        if not self.material_receipt_ref:
            return
        
        se = frappe.get_doc("Stock Entry", self.material_receipt_ref)
        
        if se.docstatus != 0:
            frappe.throw("Cannot update submitted Stock Entry")
        
        accounts = self.get_expense_accounts()
        
        se.posting_date = self.date
        se.posting_time = self.time
        se.set_posting_time = 1
        
        for item in se.items:
            if hasattr(item, 'serial_and_batch_bundle') and item.serial_and_batch_bundle:
                if frappe.db.exists("Serial and Batch Bundle", item.serial_and_batch_bundle):
                    frappe.delete_doc("Serial and Batch Bundle", item.serial_and_batch_bundle, force=1, ignore_permissions=True)
        
        se.items = []
        
        batch_items = []
        
        for idx, row in enumerate(self.manufacture_finished_goods):
            if not row.qty or row.qty <= 0:
                continue
            
            item_dict = {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "t_warehouse": row.warehouse,
                "custom_bom_qty": flt(row.bom_qty),
                "basic_rate": 1
            }
            
            if accounts.get("finished_goods_account"):
                item_dict["expense_account"] = accounts.get("finished_goods_account")
            
            if row.batch_no:
                batch_items.append({
                    'idx': idx,
                    'batch_no': row.batch_no,
                    'qty': flt(row.qty),
                    'warehouse': row.warehouse
                })
                
                try:
                    batch_doc = frappe.get_doc("Batch", row.batch_no)
                    if hasattr(batch_doc, 'manufacturing_date') and batch_doc.manufacturing_date:
                        item_dict["manufacturing_date"] = batch_doc.manufacturing_date
                    if hasattr(batch_doc, 'expiry_date') and batch_doc.expiry_date:
                        item_dict["expiry_date"] = batch_doc.expiry_date
                except:
                    pass
            else:
                has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")
                if has_batch_no:
                    item_dict["use_serial_batch_fields"] = 1
            
            se.append("items", item_dict)
        
        se.save(ignore_permissions=True)
        
        for batch_item in batch_items:
            idx = batch_item['idx']
            if idx < len(se.items):
                se_item = se.items[idx]
                bundle_name = create_batch_bundle(
                    se_item, 
                    batch_item['batch_no'], 
                    batch_item['qty'], 
                    batch_item['warehouse'], 
                    "inward",
                    se.posting_date,
                    se.posting_time
                )
                
                if bundle_name:
                    frappe.db.set_value("Stock Entry Detail", se_item.name, {
                        "serial_and_batch_bundle": bundle_name,
                        "batch_no": batch_item['batch_no']
                    })
        
        frappe.db.commit()
        se.reload()
    
    def on_cancel(self):
        self.cancel_stock_entries()
    
    def make_stock_entries(self):
        stock_entries = []
        
        if self.manufacture_raw_material:
            se_raw = self.create_stock_entry_for_raw_materials()
            if se_raw:
                stock_entries.append(se_raw)
        
        if self.manufacture_finished_goods:
            se_fg = self.create_stock_entry_for_finished_goods()
            if se_fg:
                stock_entries.append(se_fg)
        
        for se_name in stock_entries:
            frappe.db.set_value("Stock Entry", se_name, "manufacture_stock_entry", self.name)
    
    def create_stock_entry_for_raw_materials(self):
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.company = self.company
        se.posting_date = self.date
        se.posting_time = self.time
        se.set_posting_time = 1
        se.from_bom = 1 if self.from_bom else 0
        se.bom_no = self.bom_no if self.bom_no else None
        
        for item in self.manufacture_raw_material:
            item_data = {
                "item_code": item.item_code,
                "qty": flt(item.qty),
                "s_warehouse": item.warehouse,
            }
            
            if item.batch_no:
                item_data["batch_no"] = item.batch_no
            
            se.append("items", item_data)
        
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        return se.name
    
    def create_stock_entry_for_finished_goods(self):
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Manufacture"
        se.company = self.company
        se.posting_date = self.date
        se.posting_time = self.time
        se.set_posting_time = 1
        se.from_bom = 1 if self.from_bom else 0
        se.bom_no = self.bom_no if self.bom_no else None
        se.fg_completed_qty = self.finished_good_quantity if self.finished_good_quantity else 0
        
        for item in self.manufacture_finished_goods:
            item_data = {
                "item_code": item.item_code,
                "qty": flt(item.qty),
                "t_warehouse": item.warehouse,
                "is_finished_item": 1,
            }
            
            if item.batch_no:
                item_data["batch_no"] = item.batch_no
            
            se.append("items", item_data)
        
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        return se.name
    
    def cancel_stock_entries(self):
        # Cancel Material Receipt first
        if self.material_receipt_ref:
            try:
                receipt_doc = frappe.get_doc("Stock Entry", self.material_receipt_ref)
                if receipt_doc.docstatus == 1:
                    receipt_doc.flags.ignore_permissions = True
                    receipt_doc.cancel()
            except Exception as e:
                frappe.log_error(f"Error cancelling Material Receipt: {str(e)}")
        
        # Then cancel Material Issue
        if self.material_issue_ref:
            try:
                issue_doc = frappe.get_doc("Stock Entry", self.material_issue_ref)
                if issue_doc.docstatus == 1:
                    issue_doc.flags.ignore_permissions = True
                    issue_doc.cancel()
            except Exception as e:
                frappe.log_error(f"Error cancelling Material Issue: {str(e)}")
    
    def on_trash(self):
        """Delete associated Stock Entries when Manufacture Stock Entry is deleted"""
        if self.material_receipt_ref and frappe.db.exists("Stock Entry", self.material_receipt_ref):
            frappe.delete_doc("Stock Entry", self.material_receipt_ref, force=1, ignore_permissions=True)
        
        if self.material_issue_ref and frappe.db.exists("Stock Entry", self.material_issue_ref):
            frappe.delete_doc("Stock Entry", self.material_issue_ref, force=1, ignore_permissions=True)


# Helper function to create batch bundle
def create_batch_bundle(stock_entry_detail, batch_no, qty, warehouse, type_of_transaction, posting_date=None, posting_time=None):
    """
    Create Serial and Batch Bundle for a stock entry detail line
    type_of_transaction: 'outward' for Material Issue, 'inward' for Material Receipt
    """
    try:
        company = frappe.db.get_value("Stock Entry", stock_entry_detail.parent, "company")
        
        if not posting_date:
            posting_date = frappe.db.get_value("Stock Entry", stock_entry_detail.parent, "posting_date")
        if not posting_time:
            posting_time = frappe.db.get_value("Stock Entry", stock_entry_detail.parent, "posting_time")
        
        bundle = frappe.get_doc({
            "doctype": "Serial and Batch Bundle",
            "item_code": stock_entry_detail.item_code,
            "warehouse": warehouse,
            "type_of_transaction": type_of_transaction.title(),
            "company": company,
            "voucher_type": "Stock Entry",
            "posting_date": posting_date,
            "posting_time": posting_time,
            "has_batch_no": 1,
            "has_serial_no": 0
        })
        
        bundle.append("entries", {
            "batch_no": batch_no,
            "qty": flt(qty),
            "warehouse": warehouse,
            "incoming_rate": 0
        })
        
        bundle.flags.ignore_permissions = True
        bundle.insert()
        
        bundle.set_total_qty()
        bundle.save()
        
        frappe.log_error(
            f"Created batch bundle {bundle.name} for item {stock_entry_detail.item_code} with qty {qty} in batch {batch_no}", 
            "Batch Bundle Created Successfully"
        )
        
        return bundle.name
        
    except Exception as e:
        frappe.log_error(f"Error creating batch bundle: {str(e)}\nTraceback: {frappe.get_traceback()}", "Batch Bundle Creation Error")
        return None


@frappe.whitelist()
def get_item_warehouse(item_code, company):
    if not item_code or not company:
        return None
    
    item_defaults = frappe.get_all("Item Default",
        filters={
            "parent": item_code,
            "company": company
        },
        fields=["default_warehouse"],
        limit=1
    )
    
    if item_defaults and item_defaults[0].default_warehouse:
        return item_defaults[0].default_warehouse
    
    return None

@frappe.whitelist()
def get_bom_items(bom_no, type, company, finished_good_quantity=0, bom_total=0, for_production_metric_ton=0):
    if not bom_no:
        return {}
    
    bom = frappe.get_doc("BOM", bom_no)
    
    raw_materials = []
    finished_goods = []
    
    finished_good_quantity = flt(finished_good_quantity)
    bom_total = flt(bom_total)
    for_production_metric_ton = flt(for_production_metric_ton)
    
    if type == "Manufacturing":
        if finished_good_quantity <= 0:
            frappe.throw(_("Please enter Finished Good Quantity"))
        
        multiplier = finished_good_quantity / bom.quantity
        
        for item in bom.items:
            warehouse = item.source_warehouse or get_item_warehouse(item.item_code, company)
            item_name = frappe.db.get_value("Item", item.item_code, "item_name")
            raw_materials.append({
                "item_code": item.item_code,
                "item_name": item_name,
                "uom": item.uom,
                "warehouse": warehouse,
                "qty": flt(item.qty) * multiplier,
                "bom_qty": flt(item.qty)
            })
        
        fg_warehouse = bom.fg_warehouse if hasattr(bom, 'fg_warehouse') and bom.fg_warehouse else get_item_warehouse(bom.item, company)
        fg_item_name = frappe.db.get_value("Item", bom.item, "item_name")
        finished_goods.append({
            "item_code": bom.item,
            "item_name": fg_item_name,
            "uom": bom.uom,
            "warehouse": fg_warehouse,
            "qty": finished_good_quantity,
            "bom_qty": bom.quantity
        })
    
    elif type == "Premix":
        if bom_total <= 0 or for_production_metric_ton <= 0:
            frappe.throw(_("Please enter BOM Total and For Production Metric Ton"))
        
        calculated_fg_qty = bom_total * for_production_metric_ton
        multiplier = calculated_fg_qty / bom.quantity
        
        for item in bom.items:
            warehouse = item.source_warehouse or get_item_warehouse(item.item_code, company)
            item_name = frappe.db.get_value("Item", item.item_code, "item_name")
            raw_materials.append({
                "item_code": item.item_code,
                "item_name": item_name,
                "uom": item.uom,
                "warehouse": warehouse,
                "qty": flt(item.qty) * multiplier,
                "bom_qty": flt(item.qty)
            })
        
        fg_warehouse = bom.fg_warehouse if hasattr(bom, 'fg_warehouse') and bom.fg_warehouse else get_item_warehouse(bom.item, company)
        fg_item_name = frappe.db.get_value("Item", bom.item, "item_name")
        finished_goods.append({
            "item_code": bom.item,
            "item_name": fg_item_name,
            "uom": bom.uom,
            "warehouse": fg_warehouse,
            "qty": calculated_fg_qty,
            "bom_qty": bom.quantity
        })
    
    return {
        "raw_materials": raw_materials,
        "finished_goods": finished_goods,
        "bom_total": bom_total if type == "Premix" else 0,
        "finished_good_quantity": calculated_fg_qty if type == "Premix" else finished_good_quantity
    }

@frappe.whitelist()
def get_previous_finished_goods(previous_entry):
    if not previous_entry:
        return []
    
    doc = frappe.get_doc("Manufacture Stock Entry", previous_entry)
    
    raw_materials = []
    
    for item in doc.manufacture_finished_goods:
        item_name = frappe.db.get_value("Item", item.item_code, "item_name")
        raw_materials.append({
            "item_code": item.item_code,
            "item_name": item_name,
            "uom": item.uom,
            "warehouse": item.warehouse,
            "qty": item.qty,
            "bom_qty": item.bom_qty
        })
    
    return raw_materials

@frappe.whitelist()
def get_bom_total(bom_no):
    if not bom_no:
        return 0
    
    bom = frappe.get_doc("BOM", bom_no)
    return bom.quantity