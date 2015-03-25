# -*- coding: utf-8 -*-
'''

    nereid_checkout test suite

    :copyright: (c) 2010-2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import unittest
from ast import literal_eval
from mock import patch
from decimal import Decimal
from datetime import date

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.config import config
from trytond.transaction import Transaction
from nereid import current_user
from trytond import backend

from trytond.modules.nereid_cart_b2c.tests.test_product import BaseTestCase

config.set('email', 'from', 'from@xyz.com')


class BaseTestCheckout(BaseTestCase):
    """Test Checkout Base"""

    @classmethod
    def setUpClass(cls):
        print "====== Tests are running on %s ========" % backend.name()

    def setUp(self):
        super(BaseTestCheckout, self).setUp()
        trytond.tests.test_tryton.install_module('nereid_checkout')

        self.Journal = POOL.get('account.journal')
        self.Category = POOL.get('product.category')
        self.Account = POOL.get('account.account')

        self.templates.update({
            'checkout/signin.jinja': '{{form.errors|safe}}',
            'checkout/signin-email-in-use.jinja': '{{email}} in use',
            'checkout/shipping_address.jinja': '{{address_form.errors|safe}}',
            'checkout/billing_address.jinja': '{{address_form.errors|safe}}',
            'checkout/payment_method.jinja': '''[
                {{payment_form.errors|safe}},
                {{credit_card_form.errors|safe}},
            ]''',
            'emails/sale-confirmation-text.jinja': ' ',
            'emails/sale-confirmation-html.jinja': ' ',
            'checkout.jinja': '{{form.errors|safe}}',
            'sale.jinja': ' ',
            'sales.jinja': '''{{request.args.get('filter_by')}}
                {% for sale in sales %}#{{sale.id}}{% endfor %}
            '''
        })

        # Patch SMTP Lib
        self.smtplib_patcher = patch('smtplib.SMTP')
        self.PatchedSMTP = self.smtplib_patcher.start()

    def setup_defaults(self):
        """
        Setup the defaults
        """
        super(BaseTestCheckout, self).setup_defaults()

        Address = POOL.get('party.address')

        # Add emails to party
        self.Party.write([self.registered_user.party], {
            'contact_mechanisms': [('create', [
                {'type': 'email', 'value': 'test@ol.in'},
            ])],
        })

        self.Party.write([self.registered_user2.party], {
            'contact_mechanisms': [('create', [
                {'type': 'email', 'value': 'test2@ol.in'},
            ])],
        })
        # Create default addresses
        Address.create([
            {
                'party': self.registered_user.party.id,
                'name': self.registered_user.party.name,
            }, {
                'party': self.registered_user2.party.id,
                'name': self.registered_user2.party.name,
            },
        ])

        self.uom, = self.Uom.search([('symbol', '=', 'cm')])

        self.product = self.create_product()

    def create_product(self):
        """
        Create product
        """
        # Create product category
        category, = self.Category.create([{
            'name': 'Test Category',
        }])

        account_revenue, = self.Account.search([
            ('kind', '=', 'revenue')
        ])

        self.uom_kg, = self.Uom.search([('symbol', '=', 'kg')])

        # Create product
        template, = self.ProductTemplate.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'sale_uom': self.uom,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': self.uom,
            'salable': True,
            'account_revenue': account_revenue.id,
            'products': [
                ('create', [{
                    'code': 'Test Product',
                    'uri': 'test-product'
                }])
            ]
        }])

        return template.products[0]

    def _create_pricelists(self):
        """
        Create the pricelists
        """
        # Setup the pricelists
        self.party_pl_margin = Decimal('1')
        self.guest_pl_margin = Decimal('1')
        user_price_list, = self.PriceList.create([{
            'name': 'PL 1',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.party_pl_margin
                }])
            ],
        }])
        guest_price_list, = self.PriceList.create([{
            'name': 'PL 2',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.guest_pl_margin
                }])
            ],
        }])
        return guest_price_list.id, user_price_list.id

    def tearDown(self):
        # Unpatch SMTP Lib
        self.smtplib_patcher.stop()


class TestCheckoutSignIn(BaseTestCheckout):
    "Test the checkout Sign In Step"

    def test_0010_check_cart(self):
        """Assert nothing added by this module broke the cart."""
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app(DEBUG=True)

            with app.test_client() as c:
                rv = c.get('/cart')
                self.assertEqual(rv.status_code, 200)

                c.post(
                    '/cart/add', data={
                        'product': self.template1.products[0].id, 'quantity': 5
                    }
                )
                rv = c.get('/cart')
                self.assertEqual(rv.status_code, 200)

            sale, = self.Sale.search([])
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.lines[0].product, self.product1)

    def test_0015_signin_with_empty_cart(self):
        "Sign in with empty cart should redirect"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/checkout/sign-in')
                self.assertEqual(rv.status_code, 302)

    def test_0020_guest_no_email(self):
        """Submit as guest without email"""
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/sign-in')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/checkout/sign-in', data={})
                self.assertTrue('email' in rv.data)

                # Change the checkout mode to sign_in and even password
                # should become a required field
                rv = c.post(
                    '/checkout/sign-in', data={'checkout_mode': 'account'}
                )
                for field in ['email', 'password']:
                    self.assertTrue(field in rv.data)

    def test_0030_guest_valid(self):
        """Submit as guest with a new email"""
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/sign-in')
                self.assertEqual(rv.status_code, 200)

                rv = c.post(
                    '/checkout/sign-in', data={'email': 'new@openlabs.co.in'}
                )
                self.assertEqual(rv.status_code, 302)

                party, = self.Party.search([], order=[('id', 'DESC')], limit=1)
                self.assertEqual(party.email, 'new@openlabs.co.in')

    def test_0035_guest_checkout_with_regd_email(self):
        """When the user is guest and uses a registered email in the guest
        checkout, the default behavior is to show a help page in the
        template checkout/signin-email-in-use.jinja.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/sign-in')
                self.assertEqual(rv.status_code, 200)

                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': self.registered_user.email
                    }
                )
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(
                    rv.data, '%s in use' % self.registered_user.email
                )

    def test_0040_registered_user_signin_wrong(self):
        """A registered user signs in with wrong credntials"""
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'wrong_password',
                        'checkout_mode': 'account',
                    }
                )
                self.assertEqual(rv.status_code, 200)

    def test_0045_registered_user_signin(self):
        """A registered user signs in with right credntials"""
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Now sign in with the correct password
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )

    def test_0050_recent_signins_auto_proceed(self):
        "Recent signings can have an automatic proceed"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Now sign in with the correct password
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )
                rv = c.get('/checkout/sign-in')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )


class TestCheckoutShippingAddress(BaseTestCheckout):
    "Test the Shipping Address Step"

    def test_0005_no_skip_signin(self):
        "Ensure that guest orders cant directly skip to enter shipping address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/shipping-address')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/sign-in')
                )

    def test_0010_guest_get_address_page(self):
        "Guest user goes to shipping address after sign-in"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in and expect the redirect to shipping-address
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )

                # Shipping address page gets rendered
                rv = c.get('/checkout/shipping-address')
                self.assertEqual(rv.status_code, 200)

    def test_0020_guest_adds_address(self):
        "Guest user goes to shipping address after sign-in and adds address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': 'FL33137',
                        'city': 'Miami',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )

                # Assert that just one address was created
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email')
                ])
                self.assertTrue(party)
                self.assertEqual(len(party.addresses), 1)

                address, = party.addresses
                self.assertEqual(address.street, 'Biscayne Boulevard')

                self.assertEqual(
                    len(Sale.search([('shipment_address', '=', address.id)])),
                    1
                )

                # Post the address again
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': '2J Skyline Daffodil',
                        'streetbis': 'Trippunithura',
                        'zip': '682013',
                        'city': 'Cochin',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )
                # Assert that the same address was updated and a new one
                # was not created
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email')
                ])
                self.assertTrue(party)
                self.assertEqual(len(party.addresses), 1)

                address, = party.addresses
                self.assertEqual(address.street, '2J Skyline Daffodil')

                self.assertEqual(
                    len(Sale.search([('shipment_address', '=', address.id)])),
                    1
                )

    def test_0030_guest_misuse_existing_address(self):
        "Guest user fucks with the system by sending an existing address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            Address = POOL.get('party.address')
            address, = Address.search([], limit=1)

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data={'address': address.id}
                )
                self.assertEqual(rv.status_code, 200)
                form_errors = literal_eval(rv.data)
                self.assertTrue('street' in form_errors)

                self.assertEqual(
                    len(Sale.search([('shipment_address', '=', None)])), 1
                )

    def test_0040_regd_user_new_address(self):
        "Regd. user creates a new address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            Address = POOL.get('party.address')
            ContactMechanism = POOL.get('party.contact_mechanism')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': 'FL33137',
                        'phone': '1234567891',
                        'city': 'Miami',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )

                # Assert that just one address was created
                user, = self.NereidUser.search([
                    ('email', '=', 'email@example.com'),
                ])
                addresses = Address.search([
                    ('party', '=', user.party.id),
                    ('street', '=', 'Biscayne Boulevard'),
                    ('phone_number.value', '=', '1234567891'),
                ])

                self.assertEqual(len(addresses), 1)

                sales = Sale.search([
                    ('shipment_address', '=', addresses[0].id)]
                )
                self.assertEqual(len(sales), 1)

                # Post the address again, which should create another
                # address
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': '2J Skyline Daffodil',
                        'streetbis': 'Trippunithura',
                        'zip': '682013',
                        'city': 'Cochin',
                        'phone': '1234567891',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )
                # Assert that the address was created as another one
                addresses = Address.search([
                    ('party', '=', user.party.id),
                    ('street', 'in', (
                        'Biscayne Boulevard', '2J Skyline Daffodil'
                    )),
                ])
                self.assertEqual(len(addresses), 2)

                # Assert that contact mechanism is not duplicated
                phone_number = ContactMechanism.search([
                    ('type', '=', 'phone'),
                    ('party', '=', current_user.party.id),
                    ('value', '=', '1234567891'),
                ])
                self.assertEqual(len(phone_number), 1)

                # Assert the new address is now the shipment_address
                address, = Address.search([
                    ('party', '=', user.party.id),
                    ('street', '=', '2J Skyline Daffodil'),
                ])
                sales = Sale.search([
                    ('shipment_address', '=', address.id)]
                )
                self.assertEqual(len(sales), 1)

    def test_0050_regd_user_use_existing_address(self):
        "Regd. user uses one of his existing addresses"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            NereidUser = POOL.get('nereid.user')
            Address = POOL.get('party.address')

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])

            # The setup defaults creates an address, add another one
            Address.create([{
                'party': user.party.id,
                'name': 'New Address',
            }])
            addresses = Address.search([
                ('party', '=', user.party.id)
            ])
            self.assertEqual(len(addresses), 2)

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Set the first address as shipment address
                rv = c.post(
                    '/checkout/shipping-address',
                    data={'address': addresses[0].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )
                sales = Sale.search([
                    ('shipment_address', '=', addresses[0].id)]
                )
                self.assertEqual(len(sales), 1)

                # Set the second address as shipment address
                rv = c.post(
                    '/checkout/shipping-address',
                    data={'address': addresses[1].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )
                sales = Sale.search([
                    ('shipment_address', '=', addresses[1].id)]
                )
                self.assertEqual(len(sales), 1)

    def test_0060_regd_user_wrong_address(self):
        "Regd. user fucks with the system by sending someone else's address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            NereidUser = POOL.get('nereid.user')
            Address = POOL.get('party.address')

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])
            addresses = Address.search([
                ('party', '!=', user.party.id)
            ])

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Set the first address as shipment address
                rv = c.post(
                    '/checkout/shipping-address',
                    data={'address': addresses[0].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )
                sales = Sale.search([
                    ('shipment_address', '=', None)]
                )
                self.assertEqual(len(sales), 1)

    def test_0070_guest_edits_shipping_address(self):
        "Guest user wants to edit the shipping address while checkout"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Checkout = POOL.get('nereid.checkout')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                address_data = {
                    'name': 'Sharoon Thomas',
                    'street': 'Biscayne Boulevard',
                    'streetbis': 'Apt. 1906, Biscayne Park',
                    'zip': 'FL33137',
                    'city': 'Miami',
                    'country': country.id,
                    'subdivision': subdivision.id,
                }
                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data=address_data
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )

                rv = c.get('/checkout/shipping-address')
                render_obj = Checkout.shipping_address()
                self.assertTrue(render_obj)

                self.assertTrue(render_obj.context['address_form'])
                address_form = render_obj.context['address_form']
                self.assertEqual(address_form.name.data, address_data['name'])
                self.assertEqual(
                    address_form.street.data, address_data['street'])
                self.assertEqual(address_form.city.data, address_data['city'])
                self.assertEqual(
                    address_form.country.data, address_data['country'])


class TestCheckoutDeliveryMethod(BaseTestCheckout):
    "Test the Delivery Method Step"

    def test_0005_no_skip_signin(self):
        "Ensure that guest orders cant directly skip to enter delivery method"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/sign-in')
                )

    def test_0010_no_skip_signin(self):
        "Ensure that guest orders cant directly skip to enter delivery method"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Redirect to shipping address since there is no address
                # and shipment method cant be selected without a delivery
                # address
                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )


class TestCheckoutBillingAddress(BaseTestCheckout):
    "Test the Billing Address Step"

    def test_0005_no_skip_signin(self):
        "Ensure that guest orders cant directly skip to enter shipping address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/billing-address')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/sign-in')
                )

    def test_0020_guest_adds_address(self):
        "Guest user goes to billing address after sign-in and adds address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/billing-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': 'FL33137',
                        'city': 'Miami',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )

                # Assert that just one address was created
                party, = self.Party.search([
                    ('name', 'ilike', '%new@example.com%')
                ])
                self.assertTrue(party)
                self.assertEqual(len(party.addresses), 1)

                address, = party.addresses
                self.assertEqual(address.street, 'Biscayne Boulevard')

                self.assertEqual(
                    len(Sale.search([('invoice_address', '=', address.id)])),
                    1
                )

                # Post the address again
                rv = c.post(
                    '/checkout/billing-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': '2J Skyline Daffodil',
                        'streetbis': 'Trippunithura',
                        'zip': '682013',
                        'city': 'Cochin',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                # Assert that the same address was updated and a new one
                # was not created
                party, = self.Party.search([
                    ('name', 'ilike', '%new@example.com%')
                ])
                self.assertTrue(party)
                self.assertEqual(len(party.addresses), 1)

                address, = party.addresses
                self.assertEqual(address.street, '2J Skyline Daffodil')

                self.assertEqual(
                    len(Sale.search([('invoice_address', '=', address.id)])),
                    1
                )

    def test_0030_guest_misuse_existing_address(self):
        "Guest user fucks with the system by sending an existing address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            Address = POOL.get('party.address')
            address, = Address.search([], limit=1)

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/billing-address',
                    data={'address': address.id}
                )
                self.assertEqual(rv.status_code, 200)
                form_errors = literal_eval(rv.data)
                self.assertTrue('street' in form_errors)

                self.assertEqual(
                    len(Sale.search([('invoice_address', '=', None)])), 1
                )

    def test_0040_regd_user_new_address(self):
        "Regd. user creates a new address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            Address = POOL.get('party.address')
            ContactMechanism = POOL.get('party.contact_mechanism')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/billing-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': 'FL33137',
                        'city': 'Miami',
                        'phone': '1234567891',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )

                # Assert that just one address was created
                user, = self.NereidUser.search([
                    ('email', '=', 'email@example.com'),
                ])
                addresses = Address.search([
                    ('party', '=', user.party.id),
                    ('street', '=', 'Biscayne Boulevard'),
                    ('phone_number.value', '=', '1234567891'),
                ])
                self.assertEqual(len(addresses), 1)

                sales = Sale.search([
                    ('invoice_address', '=', addresses[0].id)]
                )
                self.assertEqual(len(sales), 1)

                # Post the address again, which should create another
                # address
                rv = c.post(
                    '/checkout/billing-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': '2J Skyline Daffodil',
                        'streetbis': 'Trippunithura',
                        'zip': '682013',
                        'city': 'Cochin',
                        'phone': '1234567891',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                # Assert that the address was created as another one
                addresses = Address.search([
                    ('party', '=', user.party.id),
                    ('street', 'in', (
                        'Biscayne Boulevard', '2J Skyline Daffodil'
                    )),
                ])
                self.assertEqual(len(addresses), 2)

                # Assert that contact mechanism is not duplicated
                phone_number = ContactMechanism.search([
                    ('type', '=', 'phone'),
                    ('party', '=', current_user.party.id),
                    ('value', '=', '1234567891'),
                ])
                self.assertEqual(len(phone_number), 1)

                # Assert the new address is now the shipment_address
                address, = Address.search([
                    ('party', '=', user.party.id),
                    ('street', '=', '2J Skyline Daffodil'),
                ])
                sales = Sale.search([
                    ('invoice_address', '=', address.id)]
                )
                self.assertEqual(len(sales), 1)

    def test_0050_regd_user_use_existing_address(self):
        "Regd. user uses one of his existing addresses"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            NereidUser = POOL.get('nereid.user')
            Address = POOL.get('party.address')

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])

            # The setup defaults creates an address, add another one
            Address.create([{
                'party': user.party.id,
                'name': 'New Address',
            }])
            addresses = Address.search([
                ('party', '=', user.party.id)
            ])
            self.assertEqual(len(addresses), 2)

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Set the first address as shipment address
                rv = c.post(
                    '/checkout/billing-address',
                    data={'address': addresses[0].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                sales = Sale.search([
                    ('invoice_address', '=', addresses[0].id)]
                )
                self.assertEqual(len(sales), 1)

                # Set the second address as shipment address
                rv = c.post(
                    '/checkout/billing-address',
                    data={'address': addresses[1].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                sales = Sale.search([
                    ('invoice_address', '=', addresses[1].id)]
                )
                self.assertEqual(len(sales), 1)

    def test_0060_regd_user_wrong_address(self):
        "Regd. user fucks with the system by sending someone else's address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            NereidUser = POOL.get('nereid.user')
            Address = POOL.get('party.address')

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])
            addresses = Address.search([
                ('party', '!=', user.party.id)
            ])

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Set the first address as shipment address
                rv = c.post(
                    '/checkout/billing-address',
                    data={'address': addresses[0].id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/billing-address')
                )
                sales = Sale.search([
                    ('invoice_address', '=', None)]
                )
                self.assertEqual(len(sales), 1)

    def test_0070_guest_use_delivery_as_billing(self):
        "Guest user uses shipping address for billing"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': 'FL33137',
                        'city': 'Miami',
                        'country': country.id,
                        'subdivision': subdivision.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)

                # Post to delivery-address with same flag
                rv = c.post(
                    '/checkout/billing-address',
                    data={'use_shipment_address': 'True'}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )

                # Assert that just one address was created
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email')
                ])
                self.assertTrue(party)
                self.assertEqual(len(party.addresses), 1)

                address, = party.addresses
                self.assertEqual(address.street, 'Biscayne Boulevard')

                sales = Sale.search([
                    ('shipment_address', '=', address.id),
                    ('invoice_address', '=', address.id),
                ])
                self.assertEqual(len(sales), 1)

    def test_0080_regd_use_delivery_as_billing(self):
        "Regd. user uses shipping address for billing"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')
            NereidUser = POOL.get('nereid.user')
            Address = POOL.get('party.address')

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])

            addresses = Address.search([
                ('party', '=', user.party.id)
            ])
            self.assertEqual(len(addresses), 1)

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'email@example.com',
                        'password': 'password',
                        'checkout_mode': 'account',
                    }
                )

                # Set the first address as shipment address
                rv = c.post(
                    '/checkout/shipping-address',
                    data={'address': addresses[0].id}
                )
                self.assertEqual(rv.status_code, 302)

                # Post to delivery-address with same flag
                rv = c.post(
                    '/checkout/billing-address',
                    data={'use_shipment_address': 'True'}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                sales = Sale.search([
                    ('shipment_address', '=', addresses[0].id),
                    ('invoice_address', '=', addresses[0].id),
                ])
                self.assertEqual(len(sales), 1)

    def test_0090_guest_edits_billing_address(self):
        "Guest user wants to edit the billing address while checkout"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Checkout = POOL.get('nereid.checkout')

            country = self.Country(self.available_countries[0])
            subdivision = country.subdivisions[0]

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product1.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                address_data = {
                    'name': 'Sharoon Thomas',
                    'street': 'Biscayne Boulevard',
                    'streetbis': 'Apt. 1906, Biscayne Park',
                    'zip': 'FL33137',
                    'city': 'Miami',
                    'country': country.id,
                    'subdivision': subdivision.id,
                }
                # Shipping address page gets rendered
                rv = c.post(
                    '/checkout/shipping-address',
                    data=address_data
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/validate-address')
                )

                # Post to delivery-address with same flag
                rv = c.post(
                    '/checkout/billing-address',
                    data={'use_shipment_address': 'True'}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )

                rv = c.get('/checkout/billing-address')
                render_obj = Checkout.billing_address()
                self.assertTrue(render_obj)

                self.assertTrue(render_obj.context['address_form'])
                address_form = render_obj.context['address_form']
                self.assertEqual(address_form.name.data, address_data['name'])
                self.assertEqual(
                    address_form.street.data, address_data['street'])
                self.assertEqual(address_form.city.data, address_data['city'])
                self.assertEqual(
                    address_form.country.data, address_data['country'])


class TestSale(BaseTestCheckout):
    """
    Test Sale
    """

    def test_0010_test_sale_json_ld(self):
        """
        Test the generation of json-ld for sale and sale line
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            party = self.registered_user.party

            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')

                with Transaction().set_context(company=self.company.id):
                    sale, = Sale.create([{
                        'reference': 'Sale1',
                        'sale_date': date.today(),
                        'invoice_address': party.addresses[0].id,
                        'shipment_address': party.addresses[0].id,
                        'party': party.id,
                        'lines': [
                            ('create', [{
                                'type': 'line',
                                'quantity': 2,
                                'unit': self.uom,
                                'unit_price': 200,
                                'description': 'Test description1',
                                'product': self.product.id,
                            }])
                        ]}])

                    # Test if json-ld is successfully generated for Sale
                    self.assert_(sale.as_json_ld())


def suite():
    "Checkout test suite"
    "Define suite"
    test_suite = trytond.tests.test_tryton.suite()
    loader = unittest.TestLoader()
    test_suite.addTests(
        loader.loadTestsFromTestCase(TestCheckoutSignIn),
        loader.loadTestsFromTestCase(TestCheckoutShippingAddress),
        loader.loadTestsFromTestCase(TestCheckoutDeliveryMethod),
        loader.loadTestsFromTestCase(TestCheckoutBillingAddress),
        loader.loadTestsFromTestCase(TestSale),
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
