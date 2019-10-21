# -*- coding: utf-8 -*-
##############################################################################
#                 @author IT Admin
#
##############################################################################

{
    'name': 'Punto de Venta Factura Electronica Mexico CFDI',
    'version': '1.0',
    'description': ''' Punto de Venta Factura Electronica Mexico (CFDI 3.3).
    ''',
    'category': 'Sales, Point Of Sale, Accounting',
    'author': 'IT Admin',
    'website': '',
    'depends': [
        'point_of_sale','sale','account', 'cdfi_invoice'
    ],
    'data': [
        'views/point_of_sale_view.xml',
        'wizard/create_invoice_wizard.xml',
        'wizard/create_invoice_total_wizard.xml',
        'wizard/create_invoice_session_wizard.xml',
        'data/factura_global.xml',
	],
    'qweb': [
        'static/src/xml/pos.xml',
    ],
    'application': False,
    'installable': True,
    'price': 0.00,
    'currency': 'USD',
    'license': 'OPL-1',	
}
