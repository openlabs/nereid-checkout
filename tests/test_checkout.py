# -*- coding: utf-8 -*-
'''
    
    nereid_checkout test suite
    
    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
    
'''
import doctest
from decimal import Decimal
import unittest2 as unittest
from minimock import Mock
import smtplib
smtplib.SMTP = Mock('smtplib.SMTP')
smtplib.SMTP.mock_returns = Mock('smtp_connection')

from trytond.config import CONFIG
CONFIG.options['db_type'] = 'sqlite'
CONFIG.options['data_path'] = '/tmp/temp_tryton_data/'
CONFIG['smtp_server'] = 'smtp.gmail.com'
CONFIG['smtp_user'] = 'test@xyz.com'
CONFIG['smtp_password'] = 'testpassword'
CONFIG['smtp_port'] = 587
CONFIG['smtp_tls'] = True
CONFIG['smtp_from'] = 'from@xyz.com'
from trytond.modules import register_classes
register_classes()

from trytond.modules.nereid_checkout import forms
from nereid.testing import testing_proxy, TestCase
from trytond.transaction import Transaction
from trytond.pool import Pool


class TestCheckout(TestCase):
    """Test Checkout"""

    @classmethod
    def setUpClass(cls):
        super(TestCheckout, cls).setUpClass()

        testing_proxy.install_module('nereid_checkout')

        with Transaction().start(testing_proxy.db_name, 1, None) as txn:
            uom_obj = Pool().get('product.uom')
            journal_obj = Pool().get('account.journal')
            country_obj = Pool().get('country.country')
            currency_obj = Pool().get('currency.currency')
            location_obj = Pool().get('stock.location')

            # Create company
            cls.company = testing_proxy.create_company('Test Company')
            testing_proxy.set_company_for_user(1, cls.company)
            # Create Fiscal Year
            fiscal_year = testing_proxy.create_fiscal_year(company=cls.company)
            # Create Chart of Accounts
            testing_proxy.create_coa_minimal(cls.company)
            # Create payment term
            testing_proxy.create_payment_term()

            cls.guest_user = testing_proxy.create_guest_user(company=cls.company)

            cls.available_countries = country_obj.search([], limit=5)
            cls.available_currencies = currency_obj.search([('code', '=', 'USD')])
            location, = location_obj.search([
                ('type', '=', 'storage')
            ], limit=1)
            warehouse, = location_obj.search([
                ('type', '=', 'warehouse')
            ], limit=1)
            cls.site = testing_proxy.create_site(
                'localhost', 
                countries = [('set', cls.available_countries)],
                currencies = [('set', cls.available_currencies)],
                application_user = 1, guest_user = cls.guest_user,
                stock_location = location,
                warehouse=warehouse,
            )

            testing_proxy.create_template('home.jinja', ' Home ', cls.site)
            testing_proxy.create_template('checkout.jinja', 
                '{{form.errors|safe}}', cls.site)
            testing_proxy.create_template(
                'login.jinja', 
                '{{ login_form.errors }} {{get_flashed_messages()}}', cls.site)
            testing_proxy.create_template('shopping-cart.jinja', 
                'Cart:{{ cart.id }},{{get_cart_size()|round|int}},{{cart.sale.total_amount}}', 
                cls.site)
            product_template = testing_proxy.create_template(
                'product.jinja', ' ', cls.site)
            category_template = testing_proxy.create_template(
                'category.jinja', ' ', cls.site)

            testing_proxy.create_template(
                'emails/sale-confirmation-text.jinja', ' ', cls.site)
            testing_proxy.create_template(
                'emails/sale-confirmation-html.jinja', ' ', cls.site)

            category = testing_proxy.create_product_category(
                'Category', uri='category')
            stock_journal = journal_obj.search([('code', '=', 'STO')])[0]
            cls.product = testing_proxy.create_product(
                'product 1', category,
                type = 'goods',
                salable = True,
                list_price = Decimal('10'),
                cost_price = Decimal('5'),
                account_expense = testing_proxy.get_account_by_kind('expense'),
                account_revenue = testing_proxy.get_account_by_kind('revenue'),
                uri = 'product-1',
                sale_uom = uom_obj.search([('name', '=', 'Unit')], limit=1)[0],
                )

            txn.cursor.commit()

    def get_app(self, **options):
        options.update({
            'SITE': 'localhost',
        })
        return testing_proxy.make_app(**options)

    def setUp(self):
        self.sale_obj = testing_proxy.pool.get('sale.sale')
        self.country_obj = testing_proxy.pool.get('country.country')
        self.address_obj = testing_proxy.pool.get('party.address')
        self.nereid_user_obj = testing_proxy.pool.get('nereid.user')

    def test_0010_check_cart(self):
        """Assert nothing broke the cart."""
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/cart')
            self.assertEqual(rv.status_code, 200)

            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/cart')
            self.assertEqual(rv.status_code, 200)

        with Transaction().start(testing_proxy.db_name, testing_proxy.user, None):
            sales_ids = self.sale_obj.search([])
            self.assertEqual(len(sales_ids), 1)
            sale = self.sale_obj.browse(sales_ids[0])
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.lines[0].product.id, self.product)

    def test_0020_guest_invalids(self):
        """Submit as guest and all invalids."""
        app = self.get_app()
        with app.test_client() as c:
            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/checkout')
            self.assertEqual(rv.status_code, 200)

            rv = c.post('/en_US/checkout', data={})
            # errors = json.loads(rv.data)
            for field in ['payment_method', 'shipment_method', 
                    'new_billing_address', 'new_shipping_address']:
                self.assertTrue(field in rv.data)

            rv = c.post('/en_US/checkout', data={
                'new_billing_address-city': 'Delhi',
                'shipping_same_as_billing': True,
                'payment_method': 1,
                 })
            for field in ['shipment_method', 'new_billing_address']:
                self.assertTrue(field in rv.data)
            self.assertTrue('payment_method' not in rv.data)

    def test_0030_guest_valid(self):
        """Submit as guest and all valid data."""
        app = self.get_app()

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context):
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

        with app.test_client() as c:
            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/checkout')
            self.assertEqual(rv.status_code, 200)

            data = {
                'new_billing_address-name': 'Name',
                'new_billing_address-street': 'Street',
                'new_billing_address-streetbis': 'Streetbis',
                'new_billing_address-zip': 'ZIP',
                'new_billing_address-city': 'City',
                'new_billing_address-email': 'email@example.com',
                'new_billing_address-phone': '1234567',
                'new_billing_address-country': country.id,
                'new_billing_address-subdivision': subdivision.id,
                'shipping_same_as_billing': 'Yes',
                'shipment_method': 1,
                'payment_method': 1,
            }
            rv = c.post('/en_US/checkout', data=data)
            self.assertEqual(rv.status_code, 302)

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context):
            sales_ids = self.sale_obj.search([
                ('state', '!=', 'draft'), ('is_cart', '=', True)
                ])
            self.assertEqual(len(sales_ids), 1)
            sale = self.sale_obj.browse(sales_ids[0])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0040_registered(self):
        """Invalid but with existing address chosen"""
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            regd_user_id = testing_proxy.create_user_party('Registered User', 
                'email@example.com', 'password', company=self.company)
            regd_user = self.nereid_user_obj.browse(regd_user_id)
            address_id = regd_user.addresses[0].id
            party_id = regd_user.party.id

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/en_US/login', data={
                'email': 'email@example.com',
                'password': 'password',
                })
            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/en_US/checkout', data={})
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/en_US/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/en_US/checkout', data={
                'billing_address'                   : address_id,
                'shipping_same_as_billing'          : True,
                'shipment_method'                   : 1,
                'payment_method'                    : 1,
                })
            self.assertEqual(rv.status_code, 302)

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context):
            sale_ids = self.sale_obj.search([('party', '=', party_id)])
            self.assertEqual(len(sale_ids), 1)
            sale = self.sale_obj.browse(sale_ids[0])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0050_registered_with_new_address(self):
        """Sending full address to create with registered user"""
        with Transaction().start(testing_proxy.db_name,
                testing_proxy.user, testing_proxy.context) as txn:
            regd_user_id = testing_proxy.create_user_party('Registered User 2', 
                'email2@example.com', 'password2', company=self.company)
            regd_user = self.nereid_user_obj.browse(regd_user_id)
            party_id = regd_user.party.id
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/en_US/login', data={
                'email': 'email2@example.com',
                'password': 'password2',
                })
            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/en_US/checkout', data={})
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/en_US/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/en_US/checkout', data={
                'billing_address'                   : 0,
                'new_billing_address-name'          : 'Name',
                'new_billing_address-street'        : 'Street',
                'new_billing_address-streetbis'     : 'Streetbis',
                'new_billing_address-zip'           : 'ZIP',
                'new_billing_address-city'          : 'City',
                'new_billing_address-email'         : 'email_new@example.com',
                'new_billing_address-phone'         : '1234567',
                'new_billing_address-country'       : country.id,
                'new_billing_address-subdivision'   : subdivision.id,
                'shipping_same_as_billing'          : True,
                'shipment_method'                   : 1,
                'payment_method'                    : 1,
                })
            self.assertEqual(rv.status_code, 302)

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context):
            sale_ids = self.sale_obj.search([('party', '=', party_id)])
            self.assertEqual(len(sale_ids), 1)
            sale = self.sale_obj.browse(sale_ids[0])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0060_registered_with_address_of_some_other_user(self):
        """Sending full address to create with registered user"""
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            regd_user2_id = testing_proxy.create_user_party('Registered User 3',
                'email3@example.com', 'password3', company=self.company)
            regd_user_id = self.address_obj.search([('id', '!=', regd_user2_id)])[0]
            regd_user2 = self.address_obj.browse(regd_user_id)
            party_id = regd_user2.party.id
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/en_US/login', data={
                'email': 'email3@example.com',
                'password': 'password3',
                })
            c.post('/en_US/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/en_US/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/en_US/checkout', data={})
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/en_US/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = rv.data
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/en_US/checkout', data={
                'billing_address'                   : regd_user_id,
                'shipping_same_as_billing'          : True,
                'shipment_method'                   : 1,
                'payment_method'                    : 1,
                })
            self.assertEqual(rv.status_code, 200)

def suite():
    "Checkout test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestCheckout)
    )
    suite.addTests(
        doctest.DocTestSuite(forms)
    )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
