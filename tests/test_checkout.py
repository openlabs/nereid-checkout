# -*- coding: utf-8 -*-
'''

    nereid_checkout test suite

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import unittest
import doctest
from mock import patch
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.config import CONFIG
from trytond.transaction import Transaction

from trytond.modules.nereid_checkout import forms
from trytond.modules.nereid_cart_b2c.tests.test_product import BaseTestCase

CONFIG['smtp_server'] = 'smtpserver'
CONFIG['smtp_user'] = 'test@xyz.com'
CONFIG['smtp_password'] = 'testpassword'
CONFIG['smtp_port'] = 587
CONFIG['smtp_tls'] = True
CONFIG['smtp_from'] = 'from@xyz.com'


class TestCheckout(BaseTestCase):
    """Test Checkout"""

    def setUp(self):
        super(TestCheckout, self).setUp()
        trytond.tests.test_tryton.install_module('nereid_checkout')

        self.journal_obj = POOL.get('account.journal')

        self.templates.update({
            'localhost/emails/sale-confirmation-text.jinja': ' ',
            'localhost/emails/sale-confirmation-html.jinja': ' ',
            'localhost/checkout.jinja': '{{form.errors|safe}}',
        })

        # Patch SMTP Lib
        self.smtplib_patcher = patch('smtplib.SMTP')
        self.PatchedSMTP = self.smtplib_patcher.start()

    def _create_pricelists(self):
        """
        Create the pricelists
        """
        # Setup the pricelists
        self.party_pl_margin = Decimal('1')
        self.guest_pl_margin = Decimal('1')
        user_price_list = self.pricelist_obj.create({
            'name': 'PL 1',
            'company': self.company.id,
            'lines': [
                ('create', {
                    'formula': 'unit_price * %s' % self.party_pl_margin
                })
            ],
        })
        guest_price_list = self.pricelist_obj.create({
            'name': 'PL 2',
            'company': self.company.id,
            'lines': [
                ('create', {
                    'formula': 'unit_price * %s' % self.guest_pl_margin
                })
            ],
        })
        return guest_price_list.id, user_price_list.id

    def tearDown(self):
        # Unpatch SMTP Lib
        self.smtplib_patcher.stop()

    def test_0010_check_cart(self):
        """Assert nothing added by this module broke the cart."""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/cart')
                self.assertEqual(rv.status_code, 200)

                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
                rv = c.get('/en_US/cart')
                self.assertEqual(rv.status_code, 200)

            sale, = self.sale_obj.search([])
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.lines[0].product, self.product)

    def test_0020_guest_invalids(self):
        """Submit as guest and all invalids."""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
                rv = c.get('/en_US/checkout')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/en_US/checkout', data={})
                # errors = json.loads(rv.data)
                for field in [
                        'payment_method', 'shipment_method',
                        'new_billing_address', 'new_shipping_address']:
                    self.assertTrue(field in rv.data)

                rv = c.post(
                    '/en_US/checkout', data={
                        'new_billing_address-city': 'Delhi',
                        'shipping_same_as_billing': True,
                        'payment_method': 1,
                    }
                )
                for field in ['shipment_method', 'new_billing_address']:
                    self.assertTrue(field in rv.data)
                self.assertTrue('payment_method' not in rv.data)

    def test_0030_guest_valid(self):
        """Submit as guest and all valid data."""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            country = self.country_obj(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
                rv = c.get('/en_US/checkout')
                self.assertEqual(rv.status_code, 200)

                data = {
                    'new_billing_address-name': 'Name',
                    'new_billing_address-street': 'Street',
                    'new_billing_address-streetbis': 'Streetbis',
                    'new_billing_address-zip': 'ZIP',
                    'new_billing_address-city': 'City',
                    'new_billing_address-email': 'newemail@example.com',
                    'new_billing_address-phone': '1234567',
                    'new_billing_address-country': country.id,
                    'new_billing_address-subdivision': subdivision.id,
                    'shipping_same_as_billing': 'Yes',
                    'shipment_method': 1,
                    'payment_method': 1,
                }
                rv = c.post('/en_US/checkout', data=data)
                self.assertEqual(rv.status_code, 302)

            sale, = self.sale_obj.search([
                ('state', '!=', 'draft'),
                ('is_cart', '=', True),
            ])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0035_guest_checkout_with_regd_email(self):
        """When the user is guest and uses a registered email in the guest
        checkout, the default behavior is to flash a message and redirect to
        the checkout page. Assert the behavior.
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            country = self.country_obj(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
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

            sales_ids = self.sale_obj.search([
                ('state', '!=', 'draft'), ('is_cart', '=', True)
            ])
            self.assertEqual(len(sales_ids), 0)

    def test_0040_registered(self):
        """Invalid but with existing address chosen"""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            regd_user = self.registered_user_id
            address_id = regd_user.addresses[0].id
            party_id = regd_user.party.id

            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
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
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': 0,
                        'shipping_same_as_billing': True
                    }
                )
                errors = rv.data
                self.assertTrue('payment_method' in errors)
                self.assertTrue('shipment_method' in errors)
                self.assertTrue('new_billing_address' in errors)
                self.assertTrue('shipping_address' not in errors)

                # Providing complete information
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': address_id,
                        'shipping_same_as_billing': True,
                        'shipment_method': 1,
                        'payment_method': 1,
                    }
                )
                self.assertEqual(rv.status_code, 302)

            sale, = self.sale_obj.search([('party', '=', party_id)])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0050_registered_with_new_address(self):
        """Sending full address to create with registered user"""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            regd_user = self.registered_user_id2
            party_id = regd_user.party.id
            country = self.country_obj(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                self.login(c, 'email2@example.com', 'password2')
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
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
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': 0,
                        'shipping_same_as_billing': True
                    }
                )
                errors = rv.data
                self.assertTrue('payment_method' in errors)
                self.assertTrue('shipment_method' in errors)
                self.assertTrue('new_billing_address' in errors)
                self.assertTrue('shipping_address' not in errors)

                # Providing complete information
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': 0,
                        'new_billing_address-name': 'Name',
                        'new_billing_address-street': 'Street',
                        'new_billing_address-streetbis': 'Streetbis',
                        'new_billing_address-zip': 'ZIP',
                        'new_billing_address-city': 'City',
                        'new_billing_address-email': 'email_new@example.com',
                        'new_billing_address-phone': '1234567',
                        'new_billing_address-country': country.id,
                        'new_billing_address-subdivision': subdivision.id,
                        'shipping_same_as_billing': True,
                        'shipment_method': 1,
                        'payment_method': 1,
                    }
                )
                self.assertEqual(rv.status_code, 302)

            sale, = self.sale_obj.search([('party', '=', party_id)])
            self.assertEqual(sale.total_amount, Decimal('50'))
            self.assertEqual(sale.tax_amount, Decimal('0'))
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.state, 'confirmed')

    def test_0060_registered_with_address_of_some_other_user(self):
        """Sending full address to create with registered user"""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            self.registered_user_id3 = self.nereid_user_obj.create({
                'name': 'Registered User 3',
                'display_name': 'Registered User 3',
                'email': 'email3@example.com',
                'password': 'password3',
                'company': self.company.id,
            })
            regd_user3 = self.registered_user_id3
            party_id = regd_user3.party.id

            with app.test_client() as c:
                self.login(c, 'email3@example.com', 'password3')
                c.post(
                    '/en_US/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
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
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': 0,
                        'shipping_same_as_billing': True
                    }
                )
                errors = rv.data
                self.assertTrue('payment_method' in errors)
                self.assertTrue('shipment_method' in errors)
                self.assertTrue('new_billing_address' in errors)
                self.assertTrue('shipping_address' not in errors)

                # Providing complete information
                rv = c.post(
                    '/en_US/checkout', data={
                        'billing_address': regd_user3.party.addresses[0].id,
                        'shipping_same_as_billing': True,
                        'shipment_method': 1,
                        'payment_method': 1,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/en_US/order/1/True' in rv.data)

            sale, = self.sale_obj.search([('party', '=', party_id)])


def suite():
    "Checkout test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestCheckout)
    )
    suite.addTests(doctest.DocTestSuite(forms))
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
