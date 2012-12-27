#This file is part of Tryton and Nereid.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name': 'Nereid Checkout and Default Checkout',
    'version': '2.4.0.1',
    'author': 'Openlabs Technologies & Consulting (P) LTD',
    'email': 'info@openlabs.co.in',
    'website': 'http://www.openlabs.co.in/',
    'description': '''
        Nereid Checkout
    ''',
    'depends': [
            'nereid',
            'nereid_cart_b2c',
        ],
    'xml': [
        'checkout.xml',
        'urls.xml',
        'defaults.xml',
        ],
    'translation': [
        ],
}
