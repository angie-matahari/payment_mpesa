# -*- coding: utf-8 -*-
{
    'name': "M-Pesa Payment Acquirer",

    'summary': """
        Payment Acquirer: M-Pesa Implementation""",

    'description': """
        M-Pesa Payment Acquirer
    """,

    'author': "Kylix Technologies Ltd",
    'website': "http://www.kylix.online",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting/Payment',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['payment'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/payment_mpesa_templates.xml',
    ],
    'installable': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    # please add a hook for creating or checking for KES KES.active KES.rate
    # 'uninstall_hook': 'uninstall_hook',
    
}
