#!/usr/bin/env python
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from ast import literal_eval
from decimal import Decimal
import unittest2 as unittest

from trytond.config import CONFIG
CONFIG.options['db_type'] = 'sqlite'
from trytond.modules import register_classes
register_classes()

from nereid.testing import testing_proxy
from trytond.transaction import Transaction


class TestCheckout(unittest.TestCase):
    """Test Checkout"""

    @classmethod
    def setUpClass(cls):
        # Install module
        testing_proxy.install_module('nereid_checkout')

        uom_obj = testing_proxy.pool.get('product.uom')
        journal_obj = testing_proxy.pool.get('account.journal')
        country_obj = testing_proxy.pool.get('country.country')

        with Transaction().start(testing_proxy.db_name, 1, None) as txn:
            # Create company
            company = testing_proxy.create_company('Test Company')
            testing_proxy.set_company_for_user(1, company)
            # Create Fiscal Year
            fiscal_year = testing_proxy.create_fiscal_year(company=company)
            # Create Chart of Accounts
            testing_proxy.create_coa_minimal(company)
            # Create payment term
            testing_proxy.create_payment_term()

            cls.guest_user = testing_proxy.create_guest_user()

            category_template = testing_proxy.create_template(
                'category-list.jinja', ' ')
            product_template = testing_proxy.create_template(
                'product-list.jinja', ' ')
            cls.available_countries = country_obj.search([], limit=5)
            cls.site = testing_proxy.create_site('testsite.com', 
                category_template = category_template,
                product_template = product_template,
                countries = [('set', cls.available_countries)])

            testing_proxy.create_template('home.jinja', ' Home ', cls.site)
            testing_proxy.create_template('checkout.jinja', 
                '{{form.errors}}', cls.site)
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

            category = testing_proxy.create_product_category(
                'Category', template=category_template, uri='category')
            stock_journal = journal_obj.search([('code', '=', 'STO')])[0]
            cls.product = testing_proxy.create_product(
                'product 1', category,
                type = 'stockable',
                # purchasable = True,
                salable = True,
                list_price = Decimal('10'),
                cost_price = Decimal('5'),
                account_expense = testing_proxy.get_account_by_kind('expense'),
                account_revenue = testing_proxy.get_account_by_kind('revenue'),
                nereid_template = product_template,
                uri = 'product-1',
                sale_uom = uom_obj.search([('name', '=', 'Unit')], limit=1)[0],
                #account_journal_stock_input = stock_journal,
                #account_journal_stock_output = stock_journal,
                )

            txn.cursor.commit()

    def get_app(self, **options):
        options.update({
            'SITE': 'testsite.com',
            'GUEST_USER': self.guest_user,
            })
        return testing_proxy.make_app(**options)

    def setUp(self):
        self.sale_obj = testing_proxy.pool.get('sale.sale')
        self.country_obj = testing_proxy.pool.get('country.country')
        self.address_obj = testing_proxy.pool.get('party.address')

    def test_0010_check_cart(self):
        """Assert nothing broke the cart."""
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/cart')
            self.assertEqual(rv.status_code, 200)

            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/cart')
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
            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/checkout')
            self.assertEqual(rv.status_code, 200)

            rv = c.post('/checkout', data={})
            errors = literal_eval(rv.data)
            for field in ['payment_method', 'shipment_method', 
                    'new_billing_address', 'new_shipping_address']:
                self.assertTrue(field in errors)

            rv = c.post('/checkout', data={
                'new_billing_address-city': 'Delhi',
                'shipping_same_as_billing': True,
                'payment_method': 1,
                 })
            errors = literal_eval(rv.data)
            for field in ['shipment_method', 'new_billing_address']:
                self.assertTrue(field in errors)
            self.assertTrue('payment_method' not in errors)

    def test_0030_guest_valid(self):
        """Submit as guest and all valid data."""
        app = self.get_app()

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context):
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

        with app.test_client() as c:
            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/checkout')
            self.assertEqual(rv.status_code, 200)

            rv = c.post('/checkout', data={
                'new_billing_address-name'          : 'Name',
                'new_billing_address-street'        : 'Street',
                'new_billing_address-streetbis'     : 'Streetbis',
                'new_billing_address-zip'           : 'ZIP',
                'new_billing_address-city'          : 'City',
                'new_billing_address-email'         : 'email@example.com',
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
                'email@example.com', 'password')
            regd_user = self.address_obj.browse(regd_user_id)
            party_id = regd_user.party.id

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/login', data={
                'email': 'email@example.com',
                'password': 'password',
                })
            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/checkout', data={})
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/checkout', data={
                'billing_address'                   : regd_user_id,
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
                'email2@example.com', 'password2')
            regd_user = self.address_obj.browse(regd_user_id)
            party_id = regd_user.party.id
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/login', data={
                'email': 'email2@example.com',
                'password': 'password2',
                })
            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/checkout', data={})
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/checkout', data={
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
                'email3@example.com', 'password3')
            regd_user_id = self.address_obj.search([('id', '!=', regd_user2_id)])[0]
            regd_user2 = self.address_obj.browse(regd_user_id)
            party_id = regd_user2.party.id
            country = self.country_obj.browse(self.available_countries[0])
            subdivision = country.subdivisions[0]

            txn.cursor.commit()

        app = self.get_app(DEBUG=True)
        with app.test_client() as c:
            rv = c.post('/login', data={
                'email': 'email3@example.com',
                'password': 'password3',
                })
            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/checkout')
            self.assertEqual(rv.status_code, 200)

            # Totally invalid data
            rv = c.post('/checkout', data={})
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('billing_address' in errors)
            self.assertTrue('shipping_address' in errors)

            # Invalid but providing that new_address is to be validated
            rv = c.post('/checkout', data={
                'billing_address': 0,
                'shipping_same_as_billing': True
                })
            errors = literal_eval(rv.data)
            self.assertTrue('payment_method' in errors)
            self.assertTrue('shipment_method' in errors)
            self.assertTrue('new_billing_address' in errors)
            self.assertTrue('shipping_address' not in errors)

            # Providing complete information
            rv = c.post('/checkout', data={
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
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
