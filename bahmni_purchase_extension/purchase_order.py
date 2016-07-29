from openerp.osv import fields, osv
from openerp.osv.orm import browse_null
from openerp import pooler
import openerp.addons.decimal_precision as dp
import openerp
import logging
import re

_logger = logging.getLogger(__name__)

class purchase_order(osv.osv):

    _name = "purchase.order"
    _inherit = "purchase.order"

    def _default_to_only(self, cr, uid, context=None):
        stock_warehouse_obj = self.pool.get('stock.warehouse')
        warehouse_ids = stock_warehouse_obj.search(cr, uid, [])
        return warehouse_ids[0] if (len(warehouse_ids) == 1) else False

    _defaults = {
        'warehouse_id': _default_to_only
    }

class purchase_order_line(osv.osv):

    _name = "purchase.order.line"
    _inherit = "purchase.order.line"

    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, context=None):
        res = super(purchase_order_line, self).onchange_product_id(cr, uid, ids, pricelist_id, product_id,
            qty, uom_id, partner_id, date_order, fiscal_position_id, date_planned, name, price_unit, context)

        supplierUnitConstraintWarningPattern = re.compile('The selected supplier only sells this product by .*')
        if(res.get('warning', False) and  supplierUnitConstraintWarningPattern.match(res['warning']['message'])):
            res.pop('warning', None)

        if (product_id):
            product = self.pool.get('product.product').browse(cr, uid, product_id, context)
            if (product):
                query = [('product_id','=',product_id), ('name', '=', partner_id)]
                product_supplier_info_ids = self.pool.get('product.supplierinfo').search(cr, uid, query)
                res['value']['manufacturer'] = self.get_manufacturer(cr, uid, context, product_supplier_info_ids, product)
                res['value']['price_unit'] = self.get_unit_price(cr, uid, context, product_supplier_info_ids, product)
                res['value']['mrp'] = product.get_mrp(partner_id, context=context) or False

        return res

    def get_unit_price(self, cr, uid, context, product_supplier_info_ids, product):
        pricelist_ids = product_supplier_info_ids and self.pool.get('pricelist.partnerinfo').search(cr, uid, [('suppinfo_id','=',product_supplier_info_ids[0])]) or False
        pricelist = pricelist_ids and self.pool.get('pricelist.partnerinfo').browse(cr, uid, pricelist_ids[0], context) or False

        return pricelist and pricelist.unit_price or product.standard_price

    def get_manufacturer(self, cr, uid, context, product_supplier_info_ids, product):
        product_supplier_info = product_supplier_info_ids and self.pool.get('product.supplierinfo').browse(cr, uid, product_supplier_info_ids[0], context) or False
        manufacturer_value = product_supplier_info and product_supplier_info.manufacturer or product.manufacturer or False
        return manufacturer_value

    def onchange_mrp(self, cr, uid, ids, partner_id, product_id, qty, uom_id, mrp, context=None):
        product = self.pool.get('product.product').browse(cr, uid, product_id, context=context)
        product.set_mrp(partner_id, qty, mrp, context=None)
        return {'value': {'mrp': mrp}}

    def onchange_quantity(self, cr, uid, ids, qty):
        return {'value': {
            'product_qty': qty
        }}

    def onchange_product_uom(self, cr, uid, ids, product_uom):
        return {'value': {
            'product_uom': product_uom
        }}

    def _get_product_category(self, cr, uid, ids, name, args, context=None):
        res = {}
        for purchase_order_line in self.browse(cr, uid, ids):
            product_templates =  self.pool.get('product.template').browse(cr, uid, purchase_order_line.product_id.id)
            product_category = self.pool.get('product.category').browse(cr, uid, product_templates.categ_id.id, context)
            res[purchase_order_line.id] = product_category.name
        return res

    _columns = {
        'manufacturer':fields.char('Manufacturer', size=64),
        'mrp': fields.float('MRP', required=False, digits_compute= dp.get_precision('Product Price')),
        'product_category':fields.function(_get_product_category, type='char', string='Product Category')
    }


class stock_picking_in(osv.osv):
    _name = "stock.picking.in"
    _inherit = "stock.picking.in"

    _columns = {
        'warned': fields.boolean('Warned')
    }

    _defaults = {
        'warned': False
    }

class stock_partial_picking(osv.osv_memory):
    _name = "stock.partial.picking"
    _inherit = 'stock.partial.picking'

    def do_partial(self, cr, uid, ids, context=None):
        partial = self.browse(cr, uid, ids[0], context=context)
        picking_obj = self.pool.get('stock.picking.in')
        picking = picking_obj.browse(cr, uid, context['active_id'], context=context)

        if(picking and picking.type != "internal"):
            serial_numbers = [line.prodlot_id.name for line in partial.move_ids if not isinstance(line.prodlot_id, browse_null)]
            duplicate_serial_numbers = set([sn for sn in serial_numbers if serial_numbers.count(sn) > 1])
            if(duplicate_serial_numbers):
                raise openerp.exceptions.Warning('Duplicate Serial numbers: ' + ", ".join(duplicate_serial_numbers))

            missing_serial_number = [line.product_id.name for line in partial.move_ids if isinstance(line.prodlot_id, browse_null)]
            if(not picking.warned and missing_serial_number):
                picking_obj.write(cr, uid, picking.id, {'warned': True})
                return self.pool.get('warning').warning(cr, uid, title='Empty Serial number', message="Serial number for products " + ", ".join(missing_serial_number) + " are missing. Are you sure you want to continue?")
        return super(stock_partial_picking, self).do_partial(cr, uid, ids, context=context)

stock_partial_picking()
