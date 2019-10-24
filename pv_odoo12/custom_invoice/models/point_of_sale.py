# -*- coding: utf-8 -*-

import logging
import psycopg2

from odoo import fields, models, api, _,tools, SUPERUSER_ID
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class PosConfig(models.Model):
    _inherit = 'pos.config'

    default_customer = fields.Many2one('res.partner', string=_('Cliente Default'),
                                       domain=[('customer','=',True)])
    product_total = fields.Many2one('product.product', string=_('Producto total'))


class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    main_journal_id = fields.Many2one(related='statement_ids.journal_id', string='Metodo de Pago', readonly=True, store=True)
    
    tipo_comprobante = fields.Selection(
        selection=[('I', 'Ingreso'), 
                   ('E', 'Egreso'),
                    ('T', 'Traslado'),],
        string=_('Tipo de comprobante'),
    )
    
    forma_pago = fields.Selection(
        selection=[('01', '01 - Efectivo'), 
                   ('02', '02 - Cheque nominativo'), 
                   ('03', '03 - Transferencia electrónica de fondos'),
                   ('04', '04 - Tarjeta de Crédito'), 
                   ('28', '28 - Tarjeta de débito'),],
        string=_('Forma de pago'),
    )
    #num_cta_pago = fields.Char(string=_('Núm. Cta. Pago'))
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),],
        string=_('Método de pago'), 
    )
    uso_cfdi = fields.Selection(
        selection=[('G01', _('Adquisición de mercancías')),
                   ('G02', _('Devoluciones, descuentos o bonificaciones')),
                   ('G03', _('Gastos en general')),
                   ('I01', _('Construcciones')),
                   ('I02', _('Mobiliario y equipo de oficina por inversiones')),
                   ('I03', _('Equipo de transporte')),
                   ('I04', _('Equipo de cómputo y accesorios')),
                   ('I05', _('Dados, troqueles, moldes, matrices y herramental')),
                   ('I08', _('Otra maquinaria y equipo')),
                   ('D01', _('Honorarios médicos, dentales y gastos hospitalarios')),
                   ('D02', _('Gastos médicos por incapacidad o discapacidad')),
                   ('D03', _('Gastos funerales')),
                   ('D04', _('Donativos')),
                   ('D07', _('Primas por seguros de gastos médicos')),
                   ('D08', _('Gastos de transportación escolar obligatoria')),
                   ('D10', _('Pagos por servicios educativos (colegiaturas)')),
                   ('P01', _('Por definir')),],
        string=_('Uso CFDI (cliente)'),
    )
    
    @api.model
    def get_invoice_information(self, pos_reference):
        order = self.search([('pos_reference','=',pos_reference)], limit=1)
        cfdi_vals = {'uso_cfdi':order.uso_cfdi}
        if order.partner_id:
            cfdi_vals.update({'client_name' : order.partner_id.name, 'client_rfc': order.partner_id.rfc})
        else:
            cfdi_vals.update({'client_name' : '', 'client_rfc': ''})
            
        if order.invoice_id:
            invoice = order.invoice_id
            cfdi_vals.update({
                'methodo_pago' : invoice.methodo_pago or '',
                'regimen_fiscal' : invoice.regimen_fiscal or '',
                'forma_pago' : invoice.forma_pago or '',
                'numero_cetificado' : invoice.numero_cetificado or '',
                'moneda' : invoice.moneda or '',
                'cetificaso_sat' : invoice.cetificaso_sat or '',
                'tipocambio' : invoice.tipocambio or '',
                'folio_fiscal' : invoice.folio_fiscal or '',
                'fecha_certificacion' : invoice.fecha_certificacion or '',
                'cadena_origenal' : invoice.cadena_origenal or '',
                'selo_digital_cdfi' : invoice.selo_digital_cdfi or '',
                'selo_sat' : invoice.selo_sat or '',
                'invoice_id' : invoice.id,
                'tipo_comprobante' : invoice.tipo_comprobante or 'I',
                'date_invoice' : invoice.date_invoice and invoice.date_invoice.strftime('%Y-%m-%d %H:%M:%S') or '',
                'folio_factura' : invoice.folio or '', #invoice.serie or ''  + 
                })
        else:
            cfdi_vals.update({
                'methodo_pago' : '',
                'regimen_fiscal' : '',
                'forma_pago' : '',
                'numero_cetificado' : '',
                'moneda' : '',
                'cetificaso_sat' : '',
                'tipocambio' : '',
                'folio_fiscal' : '',
                'fecha_certificacion' : '',
                'cadena_origenal' : '',
                'selo_digital_cdfi' : '',
                'selo_sat': '',
                'invoice_id' : '',
                'tipo_comprobante' : '',
                'date_invoice': '',
                'folio_factura' : '',
                })
                
        return cfdi_vals
    
    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        if 'forma_pago' in ui_order:
            res.update({'forma_pago': ui_order['forma_pago'] or None})
        if 'methodo_pago' in ui_order:
            res.update({'methodo_pago': ui_order['methodo_pago'] or None})
        if 'uso_cfdi' in ui_order:
            res.update({'uso_cfdi': ui_order['uso_cfdi'] or None})
        return res
    
    def _prepare_invoice(self):
        res = super(PosOrder, self)._prepare_invoice()
        
        res.update({'forma_pago': self.forma_pago,
                    'methodo_pago': self.methodo_pago,
                    'uso_cfdi': self.uso_cfdi,
                    'tipo_comprobante': 'I',
                    #'factura_cfdi': True,
                    })
        return res
        
    @api.multi
    def action_invoice(self, partner_total=None):
        Invoice = self.env['account.invoice']
        inv_ids = []
        invoices = {}

        note = ''
        for order in self:
            # Force company for all SUPERUSER_ID action
            local_context = dict(self.env.context, force_company=order.company_id.id, company_id=order.company_id.id)
            if order.invoice_id:
                Invoice += order.invoice_id
                continue

            if not order.partner_id and not partner_total:
                raise UserError(_('Please provide a partner for the sale.'))
            if partner_total:
                order.write({'partner_id': partner_total.id})
                
            partner = order.partner_id
            note += '%s, %s;' % (order.pos_reference, order.amount_total)
            group_key = partner.id
            
            inv_dict = order._prepare_invoice()
            inv_dict['partner_id'] = partner.id
            invoice = Invoice.new(inv_dict)
            invoice._onchange_partner_id()
            invoice.fiscal_position_id = order.fiscal_position_id

            inv = invoice._convert_to_write({name: invoice[name] for name in invoice._cache})
            inv.update({'forma_pago': order.forma_pago,
                        'methodo_pago': order.methodo_pago,
                        'uso_cfdi': order.uso_cfdi,
                        'tipo_comprobante': 'I',
                        #'factura_cfdi': True
                        })
            if group_key not in invoices:
                new_invoice = Invoice.with_context(local_context).sudo().create(inv)
                order.write({'invoice_id': new_invoice.id, 'state': 'invoiced'})
                inv_ids.append(new_invoice.id)
                invoices[group_key] = new_invoice.id
                Invoice += new_invoice
            elif group_key in invoices:
                invoice_obj = Invoice.with_context(local_context).browse(invoices[group_key])
                order.write({'invoice_id': invoice_obj.id, 'state': 'invoiced'})
                if order.name not in invoice_obj.origin.split(', '):
                    invoice_obj.write({'origin': invoice_obj.origin + ', ' + order.name})
            inv_id = invoices[group_key]
            new_invoice = Invoice.with_context(local_context).browse(inv_id)
            
            

            for line in order.lines:
                invoice_line = order.with_context(local_context)._action_create_invoice_line(line, new_invoice.id)
                if line.discount:
                    invoice_line.write({'discount':line.discount})
            new_invoice.with_context(local_context).sudo().compute_taxes()
            order.sudo().write({'state': 'invoiced'})
            new_invoice.sudo().write({'comment': note})
            if order.account_move:
                order.account_move.write({'partner_id': partner.id})
                #lines_ids = moves.mapped('lines_ids')
                order.account_move.line_ids.write({'partner_id': partner.id})
            for line in order.statement_ids:
                line.statement_id.move_line_ids.write({'partner_id':partner.id})
            # this workflow signal didn't exist on account.invoice -> should it have been 'invoice_open' ? (and now method .action_invoice_open())
            # shouldn't the created invoice be marked as paid, seing the customer paid in the POS?
            # new_invoice.sudo().signal_workflow('validate')
#            new_invoice.sudo().action_invoice_open()
#            new_invoice.sudo().force_invoice_send()

        if not Invoice:
            return {}

        return {
            'name': _('Customer Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('account.invoice_form').id,
            'res_model': 'account.invoice',
            'context': "{'type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': Invoice and Invoice.ids[0] or False,
        }

    def action_invoice_compacta(self, partner_total=None):
        inv_ref = self.env['account.invoice']
        inv_line_ref = self.env['account.invoice.line']
        #product_obj = self.pool.get('product.product')
        inv_ids = []
        invoices = {}

        note = ''
        for order in self:
            # Force company for all SUPERUSER_ID action
            company_id = order.company_id.id
            local_context = dict(self._context.copy() or {}, force_company=company_id, company_id=company_id)
            if order.invoice_id:
                inv_ids.append(order.invoice_id)
                continue

            if not order.partner_id and not partner_total:
                raise UserError(_('Please provide a partner for the sale.'))
            
            note += '%s, %s;' % (order.pos_reference, order.amount_total)
            partner = order.partner_id and order.partner_id or partner_total
            group_key = partner.id

            acc = partner.property_account_receivable_id.id
            inv = {
                'name': order.name,
                'origin': order.name,
                'account_id': acc,
                'journal_id': order.sale_journal.id or None,
                'type': 'out_invoice',
                'reference': order.name,
                'partner_id': partner.id,
                'comment': note,
                'currency_id': order.pricelist_id.currency_id.id, # considering partner's sale pricelist's currency
                'company_id': company_id,
                'user_id': self._uid,
            }
            inv.update({'forma_pago': order.forma_pago,
                        'methodo_pago': order.methodo_pago,
                        'uso_cfdi': order.uso_cfdi,
                        'tipo_comprobante': 'I',
                        'factura_cfdi': True
                        })
            invoice = inv_ref.new(inv)
            invoice._onchange_partner_id()

            inv = invoice._convert_to_write(invoice._cache)
            if not inv.get('account_id', None):
                inv['account_id'] = acc
            if group_key not in invoices:
                invoice_rec = inv_ref.sudo().with_context(local_context).create(inv)
                order.write({'invoice_id': invoice_rec.id, 'state': 'invoiced'})
                inv_ids.append(invoice_rec)
                invoices[group_key] = invoice_rec
            elif group_key in invoices:
                invoice_obj = invoices[group_key]
                order.write({'invoice_id': invoice_obj.id, 'state': 'invoiced'})
                if order.name not in invoice_obj.origin.split(', '):
                    invoice_obj.sudo().with_context(local_context).write({'origin': invoice_obj.origin + ', ' + order.name})
            invoice_rec = invoices[group_key]
            for line in order.lines:
                line_exist = invoice_rec.invoice_line_ids.filtered(lambda x:x.product_id.id==line.product_id.id)
                if line_exist:
                    line_taxes = line.tax_ids_after_fiscal_position.ids
                    is_line_matched=False
                    for inn_line in line_exist: 
                        invoice_line_taxes = inn_line.invoice_line_tax_ids.ids
                        if set(line_taxes)==set(invoice_line_taxes):
                            if line.discount:
                                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                            else:
                                price = line.price_unit
                            total_price = inn_line.quantity * inn_line.price_unit
                            total_price += line.qty * price
                            
                            total_qty = inn_line.quantity + line.qty
                            price_unit = total_price/total_qty
                            
                            inn_line.write({'quantity':total_qty,'price_unit' : price_unit})
                            is_line_matched=True
                            break
                    if is_line_matched:
                        continue
                
                inv_name = line.product_id.with_context(context=local_context).name_get()[0][1]
                inv_line = {
                    'invoice_id': invoice_rec.id,
                    'product_id': line.product_id.id,
                    'quantity': line.qty,
                    'account_analytic_id': self._prepare_analytic_account(line),
                    'name': inv_name,
                }

                #Oldlin trick
                invoice_line = inv_line_ref.sudo().with_context(local_context).new(inv_line)
                invoice_line._onchange_product_id()
                
                invoice_line.invoice_line_tax_ids = [tax.id for tax in line.tax_ids_after_fiscal_position] #if tax.company_id.id == company_id
                #fiscal_position_id = line.order_id.fiscal_position_id
                #if fiscal_position_id:
                #    invoice_line.invoice_line_tax_ids = fiscal_position_id.map_tax(invoice_line.invoice_line_tax_ids)
                #invoice_line.invoice_line_tax_ids = [tax.id for tax in invoice_line.invoice_line_tax_ids]
                # We convert a new id object back to a dictionary to write to bridge between old and new api
                inv_line = invoice_line._convert_to_write(invoice_line._cache)
                if line.discount:
                    price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                else:
                    price = line.price_unit
                inv_line.update(price_unit=price) #, discount=line.discount
                inv_line_ref.sudo().with_context(local_context).create(inv_line)
            invoice_rec.with_context(local_context).compute_taxes()
            invoice_rec.with_context(local_context).write({'comment': note})
            
            #order.signal_workflow('invoice')
        
            if order.account_move:
                order.account_move.sudo().with_context(local_context).write({'partner_id': partner.id})
                order.account_move.line_ids.sudo().write({'partner_id': partner.id},)
            for line in order.statement_ids:
                #print 'line.statement_id.move_line_ids.ids: ', line.statement_id.move_line_ids
                line.statement_id.move_line_ids.sudo().write({'partner_id': partner.id}, )
        #for invoice in invoices.values():
        #   invoice.sudo().action_invoice_open()
            #invoice.sudo().signal_workflow('validate')
            #inv_ref.signal_workflow(cr, SUPERUSER_ID, [inv_id], 'validate')
            # inv_ref.force_invoice_send(cr, SUPERUSER_ID, [inv_id], context=context)

        if not inv_ids: return {}

        mod_obj = self.env['ir.model.data']
        res = mod_obj.get_object_reference('account', 'invoice_form')
        res_id = res and res[1] or False
        return {
            'name': _('Customer Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': [res_id],
            'res_model': 'account.invoice',
            'context': "{'type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'target': 'current',
            'res_id': inv_ids and inv_ids[0].id or False,
        }        
    
    @api.model
    def create_from_ui(self, orders):
        # Keep only new orders
        submitted_references = [o['data']['name'] for o in orders]
        pos_order = self.search([('pos_reference', 'in', submitted_references)])
        existing_orders = pos_order.read(['pos_reference'])
        existing_references = set([o['pos_reference'] for o in existing_orders])
        orders_to_save = [o for o in orders if o['data']['name'] not in existing_references]
        order_ids = []

        for tmp_order in orders_to_save:
            to_invoice = tmp_order['to_invoice']
            order = tmp_order['data']
            if to_invoice:
                self._match_payment_to_invoice(order)
            pos_order = self._process_order(order)
            order_ids.append(pos_order.id)

            try:
                pos_order.action_pos_order_paid()
            except psycopg2.OperationalError:
                # do not hide transactional errors, the order(s) won't be saved!
                raise
            except Exception as e:
                _logger.error('Could not fully process the POS Order: %s', tools.ustr(e))

            if to_invoice:
                pos_order.action_pos_order_invoice()
                pos_order.invoice_id.sudo().action_invoice_open()
                pos_order.account_move = pos_order.invoice_id.move_id
                #Added
                pos_order.invoice_id.sudo().action_cfdi_generate()
                pos_order.invoice_id.sudo().force_invoice_send()
        return order_ids


    @api.multi
    def action_invoice_total(self, product_total=None, partner_total=None, invoice_format=None):
        inv_ref = self.env['account.invoice']
        inv_line_ref = self.env['account.invoice.line']
        inv_ids = []
        
        if not product_total:
            raise UserError(_('Please provide a product total.'))
        
#         if not product_total:
#             raise UserError(_('Please provide a product total.'))
        note = ''
        origin = []
        if not partner_total:
            raise UserError(_('Please provide a partner for the sale.'))
        
        #taxes_group = defaultdict(self.env['account.tax'].browse)
        partner = partner_total
        if not self:
            return
        sale_journal = self[0].sale_journal
        company_id = self[0].company_id.id
        local_context = dict(self.env.context, force_company=self[0].company_id.id, company_id=self[0].company_id.id)
        orders = self.browse()    
        taxes_group  = {}
        for order in self:
            if order.invoice_id:
                inv_ids.append(order.invoice_id.id)
                continue
            if partner_total:
                order.update({'partner_id': partner_total.id})
             
            for line in order.lines:
                if invoice_format=='cfdi':
                    if (line.tax_ids_after_fiscal_position,order) not in taxes_group:
                        taxes_group.update({(line.tax_ids_after_fiscal_position,order):line})
                    else:
                        taxes_group[(line.tax_ids_after_fiscal_position,order)] +=line
                else:
                    if (line.tax_ids_after_fiscal_position,self) not in taxes_group:
                        taxes_group.update({(line.tax_ids_after_fiscal_position,self):line})
                    else:
                        taxes_group[(line.tax_ids_after_fiscal_position,self)] +=line
                    #taxes_group[line.tax_ids_after_fiscal_position] |= line
            if order.pos_reference:
                note += '%s, %s;' % (order.pos_reference.replace('Pedido ',''), order.amount_total)
            else:
                note += '%s;' % (order.amount_total)
            origin.append(order.name)
            
            if order.account_move:
                order.account_move.write({'partner_id': partner.id})
                order.account_move.line_ids.write({'partner_id': partner.id})
            for line in order.statement_ids:
                line.statement_id.move_line_ids.write({'partner_id':partner.id})
            orders += order
                
        if taxes_group:
            acc = partner.property_account_receivable_id.id
            inv = {
                'name': origin and origin[0],
                'origin': ', '.join(origin),
                'account_id': acc,
                'journal_id': sale_journal and sale_journal.id or None,
                'type': 'out_invoice',
                'reference': origin and origin[0],
                'partner_id': partner.id,
                'comment': note or '',
                'currency_id': self[0].pricelist_id.currency_id.id, # considering partner's sale pricelist's currency
                'company_id': company_id,
                'user_id': self.env.uid,
                'forma_pago': '01',
                'methodo_pago': 'PUE',
                'uso_cfdi': 'P01',
                'tipo_comprobante': 'I',
            }
            invoice = inv_ref.new(inv)
            invoice._onchange_partner_id()
    
            inv = invoice._convert_to_write({name: invoice[name] for name in invoice._cache})
            if not inv.get('account_id', None):
                inv['account_id'] = acc
            invoice = inv_ref.with_context(local_context).sudo().create(inv)
            inv_id = invoice.id
            inv_ids.append(inv_id)
            for order_taxes, order_lines in taxes_group.items():
                taxes = order_taxes[0]
                
                price_unit = 0.0
                for line in order_lines:
                    if line.discount:
                        price_unit += (line.price_unit * (1 - (line.discount or 0.0) / 100.0))*line.qty
                    else:
                        price_unit += line.price_unit*line.qty
                #price_unit = sum([line.qty*line.price_unit for line in order_lines])
                #inv_line_name = product_total.name
                if order_taxes[1]:
                    if order_taxes[1][0].pos_reference:
                        inv_line_name = (invoice_format == 'cfdi') and '[%s] %s' % (order_taxes[1].pos_reference.replace('Pedido ',''), product_total.name) or  product_total.name
                    else:
                        inv_line_name = (invoice_format == 'cfdi') and '[%s] %s' % (order_taxes[1][0].name, product_total.name) or  product_total.name
                inv_line = {
                    'invoice_id': inv_id,
                    'product_id': product_total.id,
                    'price_unit': price_unit,
                    'quantity': 1,
                    'name': inv_line_name,
                }
                invoice_line = inv_line_ref.new(inv_line)
                invoice_line._onchange_product_id()
                invoice_line.invoice_line_tax_ids = [tax.id for tax in taxes]
                # We convert a new id object back to a dictionary to write to bridge between old and new api
                inv_line = invoice_line._convert_to_write({name: invoice_line[name] for name in invoice_line._cache})
                inv_line.update({'price_unit': price_unit,'name': inv_line_name,})
                inv_line_id = inv_line_ref.create(inv_line)
            
            invoice.with_context(local_context).sudo().compute_taxes()
            orders.sudo().write({'state': 'invoiced', 'invoice_id': inv_id})
           

        if not inv_ids: return {}

        return {
            'name': _('Customer Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'res_model': 'account.invoice',
            'context': {},
            'type': 'ir.actions.act_window',
            'res_id': inv_ids[0],
        }