# -*- coding: utf-8 -*-
'''

    Tests payment

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import unittest
import random
from ast import literal_eval
from decimal import Decimal
import json
from datetime import date

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.config import config
from trytond.transaction import Transaction
from nereid import current_user

from test_checkout import BaseTestCheckout

config.set('email', 'from', 'from@xyz.com')


class TestCheckoutPayment(BaseTestCheckout):
    "Test the payment Step"

    def setUp(self):
        super(TestCheckoutPayment, self).setUp()
        trytond.tests.test_tryton.install_module(
            'payment_gateway_authorize_net'
        )

    def _process_sale_by_completing_payments(self, sales):
        """Process sale and complete payments.
        """
        self.Sale.process(sales)
        self.Sale.complete_payments()

    def create_payment_profile(self, party, gateway):
        """
        Create a payment profile for the party
        """
        AddPaymentProfileWizard = POOL.get(
            'party.party.payment_profile.add', type='wizard'
        )

        # create a profile
        profile_wiz = AddPaymentProfileWizard(
            AddPaymentProfileWizard.create()[0]
        )
        profile_wiz.card_info.party = party.id
        profile_wiz.card_info.address = party.addresses[0].id
        profile_wiz.card_info.provider = gateway.provider
        profile_wiz.card_info.gateway = gateway
        profile_wiz.card_info.owner = party.name
        profile_wiz.card_info.number = '4111111111111111'
        profile_wiz.card_info.expiry_month = '11'
        profile_wiz.card_info.expiry_year = '2018'
        profile_wiz.card_info.csc = '353'

        with Transaction().set_context(return_profile=True):
            return profile_wiz.transition_add()

    def _create_regd_user_order(self, client, quantity=None):
        """
        A helper function that creates an order for a regd user.

        This is to avoid clutter within the tests below
        """
        if not quantity:
            quantity = random.randrange(10, 100)
        client.post(
            '/cart/add', data={
                'product': self.product1.id,
                'quantity': quantity,
            }
        )

        # Sign-in
        rv = client.post(
            '/checkout/sign-in', data={
                'email': 'email@example.com',
                'password': 'password',
                'checkout_mode': 'account',
            }
        )

        country = self.Country(self.available_countries[0])
        subdivision = country.subdivisions[0]

        rv = client.post(
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

        # Post to payment delivery-address with same flag
        rv = client.post(
            '/checkout/payment',
            data={'use_shipment_address': 'True'}
        )
        self.assertEqual(rv.status_code, 200)

    def _create_guest_order(self, client, quantity=None):
        """
        A helper function that creates an order for a guest user.

        This is to avoid clutter within the tests below
        """
        if not quantity:
            quantity = random.randrange(10, 100)
        client.post(
            '/cart/add', data={
                'product': self.product1.id,
                'quantity': quantity
            }
        )

        # Sign-in
        rv = client.post(
            '/checkout/sign-in', data={
                'email': 'new@example.com',
                'checkout_mode': 'guest',
            }
        )

        country = self.Country(self.available_countries[0])
        subdivision = country.subdivisions[0]

        rv = client.post(
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

        # Post to payment delivery-address with same flag
        rv = client.post(
            '/checkout/payment',
            data={'use_shipment_address': 'True'}
        )
        self.assertEqual(rv.status_code, 200)

    def _create_cheque_payment_method(self):
        """
        A helper function that creates the cheque gateway and assigns
        it to the websites.
        """
        PaymentGateway = POOL.get('payment_gateway.gateway')
        NereidWebsite = POOL.get('nereid.website')
        PaymentMethod = POOL.get('nereid.website.payment_method')
        Journal = POOL.get('account.journal')

        cash_journal, = Journal.search([
            ('name', '=', 'Cash')
        ])

        gateway = PaymentGateway(
            name='Offline Payment Methods',
            journal=cash_journal,
            provider='self',
            method='manual',
        )
        gateway.save()

        website, = NereidWebsite.search([])

        payment_method = PaymentMethod(
            name='Cheque',
            gateway=gateway,
            website=website
        )
        payment_method.save()
        return payment_method

    def _create_auth_net_gateway_for_site(self):
        """
        A helper function that creates the authorize.net gateway and assigns
        it to the websites.
        """
        PaymentGateway = POOL.get('payment_gateway.gateway')
        NereidWebsite = POOL.get('nereid.website')
        Journal = POOL.get('account.journal')

        cash_journal, = Journal.search([
            ('name', '=', 'Cash')
        ])

        gateway = PaymentGateway(
            name='Authorize.net',
            journal=cash_journal,
            provider='authorize_net',
            method='credit_card',
            authorize_net_login='327deWY74422',
            authorize_net_transaction_key='32jF65cTxja88ZA2',
            test=True
        )
        gateway.save()

        websites = NereidWebsite.search([])
        NereidWebsite.write(websites, {
            'accept_credit_card': True,
            'save_payment_profile': True,
            'credit_card_gateway': gateway.id,
        })
        return gateway

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
                rv = c.get('/checkout/payment')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/sign-in')
                )

    def test_0010_no_skip_shipping_address(self):
        """
        Ensure that guest orders cant directly skip to payment without a
        valid shipment_address.

        Once shipment address is there, it should be possible to get the
        page even without a invoice_address
        """

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

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

                # redirect to shipment address page
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )

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

                rv = c.get('/checkout/payment')
                self.assertEqual(rv.status_code, 200)

    def test_0020_no_skip_invoice_address(self):
        """
        While possible to view the payment_method page without a
        billing_address, it should not be possible to complete payment without
        it.
        """

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

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

                # GET requetss get served
                rv = c.get('/checkout/payment')
                self.assertEqual(rv.status_code, 200)

                # POST redirects to billing address
                rv = c.post('/checkout/payment', data={})

                # redirect to shipment address page
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/billing-address')
                )

    def test_0030_address_with_payment(self):
        "Send address along with payment"
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

                # Post to payment delivery-address with same flag
                rv = c.post(
                    '/checkout/payment',
                    data={'use_shipment_address': 'True'}
                )
                self.assertEqual(rv.status_code, 200)

                # Assert that just one address was created
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email'),
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

    def test_0100_guest_credit_card(self):
        "Guest - Credit Card"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            with app.test_client() as c:
                self._create_guest_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                    }
                )
                # though the card is there, the website is not configured
                # to accept credit_Card as there is no gateway defined.
                self.assertEqual(rv.status_code, 200)

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_guest_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                self.assertTrue('access_code' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])
                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertFalse(sale.payment_available)
                self.assertTrue(sale.email_sent)

    def test_0105_update_guest_name_with_address_name(self):
        "Check if guest user name is updated as per billing address"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            with app.test_client() as c:
                self._create_guest_order(c)

                # Define a new payment gateway
                self._create_auth_net_gateway_for_site()

                # Check party name on checkout
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email')
                ])
                self.assertEqual(
                    party.name, 'Guest with email: new@example.com'
                )

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                self.assertTrue('access_code' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Party name is updated with the name on shipping address
                party, = self.Party.search([
                    ('contact_mechanisms.value', '=', 'new@example.com'),
                    ('contact_mechanisms.type', '=', 'email')
                ])
                self.assertEqual(party.name, 'Sharoon Thomas')

    def test_0110_guest_alternate_payment(self):
        "Guest - Alternate Payment Method"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            # Define a new payment gateway
            cheque_method = self._create_cheque_payment_method()

            with app.test_client() as c:
                self._create_guest_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={'alternate_payment_method': cheque_method.id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                self.assertTrue('access_code' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])
                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertEqual(payment_transaction.state, 'completed')

    def test_0120_guest_profile_fail(self):
        "Guest - Fucks with profile"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_guest_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment', data={
                        'payment_profile': 1
                    }
                )
                self.assertEqual(rv.status_code, 200)
                payment_form_errors, _ = literal_eval(rv.data)

                self.assertTrue('payment_profile' in payment_form_errors)

    def test_0200_regd_new_credit_card_wo_save(self):
        "Regd User - Credit Card"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': '',
                    }
                )
                # though the card is there, the website is not configured
                # to accept credit_Card as there is no gateway defined.
                self.assertEqual(rv.status_code, 200)

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': '',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])

                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)

                self.assertFalse(sale.payment_available)

                # Payment profile will get saved always.
                self.assertEqual(len(sale.party.payment_profiles), 1)

    def test_0205_regd_new_credit_card(self):
        "Regd User - Credit Card and save it"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': 'y',
                    }
                )
                # though the card is there, the website is not configured
                # to accept credit_Card as there is no gateway defined.
                self.assertEqual(rv.status_code, 200)

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': 'y',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])

                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertFalse(sale.payment_available)

                # Ensure that the card is NOT saved
                self.assertEqual(len(sale.party.payment_profiles), 1)

    def test_0210_regd_alternate_payment(self):
        "Regd User - Alternate Payment Method"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            # Define a new payment gateway
            cheque_method = self._create_cheque_payment_method()

            with app.test_client() as c:
                self._create_regd_user_order(c, 10)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={'alternate_payment_method': cheque_method.id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])

                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertEqual(payment_transaction.state, 'completed')

    def test_0220_regd_profile_fail(self):
        "Regd User - Fucks with profile"
        NereidUser = POOL.get('nereid.user')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            user, = NereidUser.search([
                ('email', '=', 'email@example.com')
            ])

            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment', data={
                        'payment_profile': 1
                    }
                )
                self.assertEqual(rv.status_code, 200)
                payment_form_errors, _ = literal_eval(rv.data)

                self.assertTrue('payment_profile' in payment_form_errors)

    def test_0225_regd_profile_success(self):
        "Regd User - Correct with profile"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': 'y',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])

                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertFalse(sale.payment_available)

                # Ensure that the card is saved
                self.assertEqual(len(sale.party.payment_profiles), 1)

            payment_profile, = sale.party.payment_profiles

            with app.test_client() as c:
                self._create_regd_user_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={'payment_profile': payment_profile.id}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = Sale.search([
                    ('id', '!=', sale.id),  # Not previous sale
                    ('state', '=', 'confirmed'),
                ])

                # Process sale with payments
                self._process_sale_by_completing_payments([sale])

                payment_transaction, = sale.gateway_transactions
                self.assertEqual(payment_transaction.amount, sale.total_amount)
                self.assertFalse(sale.payment_available)

                # Ensure that the card is saved (the original one)
                self.assertEqual(len(sale.party.payment_profiles), 1)

    def test_0230_validate_payment_profile(self):
        """
        Selecting billing address as saved address in payment profile
        """

        Address = POOL.get('party.address')
        Profile = POOL.get('party.payment_profile')
        Gateway = POOL.get('payment_gateway.gateway')
        Journal = POOL.get('account.journal')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            self.party2, = self.Party.create([{
                'name': 'Registered User',
            }])
            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')

                address, = Address.create([{
                    'party': current_user.party.id,
                    'name': 'Name',
                    'street': 'Street',
                    'streetbis': 'StreetBis',
                    'zip': 'zip',
                    'city': 'City',
                    'country': self.available_countries[0].id,
                    'subdivision':
                        self.available_countries[0].subdivisions[0].id,
                }])
                self._create_auth_net_gateway_for_site()
                self.assertEqual(
                    len(current_user.party.payment_profiles), 0
                )

                gateway, = Gateway.search(['name', '=', 'Authorize.net'])

                cash_journal, = Journal.search([
                    ('name', '=', 'Cash')
                ])
                profile, = Profile.create([{
                    'last_4_digits': '1111',
                    'sequence': '10',
                    'expiry_month': '01',
                    'expiry_year': '2018',
                    'address': address.id,
                    'party': current_user.party.id,
                    'provider_reference': '26037832',
                    'gateway': gateway.id,
                    'authorize_profile_id': '28545177',
                }])
                self.assertEqual(
                    len(current_user.party.payment_profiles), 1
                )

                self._create_regd_user_order(c)
                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'payment_profile': '23'
                    }
                )

                self.assertTrue(
                    "Not a valid choice" in rv.data
                )

                self._create_regd_user_order(c)
                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'payment_profile':
                        current_user.party.payment_profiles[0].id
                    }
                )

                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                sale, = self.Sale.search([('state', '=', 'confirmed')])
                self.assertEqual(sale.invoice_address.id, address.id)

    def test_0240_add_comment_to_sale(self):
        """
        Add comment to sale for logged in user.
        """
        Address = POOL.get('party.address')
        Profile = POOL.get('party.payment_profile')
        Gateway = POOL.get('payment_gateway.gateway')
        Journal = POOL.get('account.journal')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            self.party2, = self.Party.create([{
                'name': 'Registered User',
            }])
            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')
                address, = Address.create([{
                    'party': current_user.party.id,
                    'name': 'Name',
                    'street': 'Street',
                    'streetbis': 'StreetBis',
                    'zip': 'zip',
                    'city': 'City',
                    'country': self.available_countries[0].id,
                    'subdivision':
                        self.available_countries[0].subdivisions[0].id,
                }])
                self._create_auth_net_gateway_for_site()
                self.assertEqual(
                    len(current_user.party.payment_profiles), 0
                )

                gateway, = Gateway.search(['name', '=', 'Authorize.net'])

                cash_journal, = Journal.search([
                    ('name', '=', 'Cash')
                ])
                profile, = Profile.create([{
                    'last_4_digits': '1111',
                    'sequence': '10',
                    'expiry_month': '01',
                    'expiry_year': '2018',
                    'address': address.id,
                    'party': current_user.party.id,
                    'provider_reference': '26037832',
                    'gateway': gateway.id,
                    'authorize_profile_id': '28545177',
                }])
                self.assertEqual(
                    len(current_user.party.payment_profiles), 1
                )

                self._create_regd_user_order(c)
                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'payment_profile':
                        current_user.party.payment_profiles[0].id
                    }
                )

                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)

                sale, = self.Sale.search([('state', '=', 'confirmed')])
                rv = c.post(
                    '/order/%s/add-comment' % (sale.id,), data={
                        'comment': 'This is comment on sale!'
                    }, headers=[('X-Requested-With', 'XMLHttpRequest')]
                )

                json_data = json.loads(rv.data)['message']
                self.assertEqual('Comment Added', json_data)

                self.assertEqual('This is comment on sale!', sale.comment)

                rv = c.post(
                    '/order/%s/add-comment' % (sale.id,), data={
                        'comment': 'This is comment!'
                    }
                )
                self.assertTrue(rv.status_code, 302)

    def test_0245_no_comment_on_cancelled_sale(self):
        """
        Trying to comment on a cancelled sale should return 403.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')

                # Create sale.
                sale, = self.Sale.create([{
                    'party': self.registered_user.party.id,
                    'company': self.company.id,
                    'currency': self.usd.id,
                }])

                # Cancel the sale order now.
                self.Sale.cancel([sale])

                # Try commenting.
                rv = c.post(
                    '/order/%s/add-comment' % (sale.id,), data={
                        'comment': 'This is comment!'
                    }
                )
                self.assertEqual(rv.status_code, 403)

    def test_0250_add_comment_to_guest_sale(self):
        """
        Add comment to sale for guest user
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            with app.test_client() as c:
                self._create_guest_order(c)

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_guest_order(c)

                # Try to pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                self.assertTrue('access_code' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                rv = c.post(
                    '/order/%s/add-comment' % (sale.id, ), data={
                        'comment': 'This is comment on sale!'
                    }, headers=[('X-Requested-With', 'XMLHttpRequest')]
                )
                self.assertEqual(rv.status_code, 403)

                rv = c.post(
                    '/order/%s/add-comment?access_code=%s' % (
                        sale.id, sale.guest_access_code,
                    ), data={
                        'comment': 'This is comment on sale!'
                    }, headers=[('X-Requested-With', 'XMLHttpRequest')]
                )

                json_data = json.loads(rv.data)['message']
                self.assertEqual('Comment Added', json_data)

                self.assertEqual('This is comment on sale!', sale.comment)

    def test_0300_access_order_page(self):
        """
        Test access order page
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            # Define a new payment gateway
            self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_guest_order(c)

                # pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                    }
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue('/order/' in rv.location)
                self.assertTrue('access_code' in rv.location)

                sale, = Sale.search([('state', '=', 'confirmed')])

                rv = c.get('/order/%s' % (sale.id, ))
                self.assertEqual(rv.status_code, 302)  # Redirect to login

                rv = c.get(
                    '/order/%s?access_code=%s' % (sale.id, "wrong-access-code")
                )
                self.assertEqual(rv.status_code, 403)

                rv = c.get(
                    '/order/%s?access_code=%s' % (
                        sale.id, sale.guest_access_code
                    )
                )
                self.assertEqual(rv.status_code, 200)

    def test_0305_orders_page_regd(self):
        """
        Accesses orders page for a registered user.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            Sale = POOL.get('sale.sale')

            party = self.registered_user.party

            with app.test_client() as c:
                self.login(c, 'email@example.com', 'password')

                # Create sales.
                with Transaction().set_context(company=self.company.id):
                    sale1, = Sale.create([{
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
                    sale2, = Sale.create([{
                        'reference': 'Sale2',
                        'sale_date': date.today(),
                        'invoice_address': party.addresses[0].id,
                        'shipment_address': party.addresses[0].id,
                        'state': 'done',  # For testing purpose.
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
                    sale3, = Sale.create([{
                        'reference': 'Sale3',
                        'sale_date': date.today(),
                        'invoice_address': party.addresses[0].id,
                        'shipment_address': party.addresses[0].id,
                        'party': party.id,
                        'sale_date': '2014-06-06',  # For testing purpose.
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

                Sale.quote([sale1])
                Sale.confirm([sale1])

                rv = c.get('/orders?filter_by=recent')
                self.assertIn('recent', rv.data)
                self.assertIn('#{0}'.format(sale1.id), rv.data)
                self.assertIn('#{0}'.format(sale2.id), rv.data)
                self.assertNotIn('#{0}'.format(sale3.id), rv.data)

                rv = c.get('/orders?filter_by=done')
                self.assertIn('done', rv.data)
                self.assertIn('#{0}'.format(sale2.id), rv.data)
                self.assertNotIn('#{0}'.format(sale1.id), rv.data)
                self.assertNotIn('#{0}'.format(sale3.id), rv.data)

                Sale.cancel([sale3])

                rv = c.get('/orders?filter_by=canceled')
                self.assertIn('cancel', rv.data)
                self.assertIn('#{0}'.format(sale3.id), rv.data)
                self.assertNotIn('#{0}'.format(sale1.id), rv.data)
                self.assertNotIn('#{0}'.format(sale2.id), rv.data)

                rv = c.get('/orders?filter_by=archived')
                self.assertIn('archived', rv.data)
                self.assertIn('#{0}'.format(sale3.id), rv.data)
                self.assertNotIn('#{0}'.format(sale1.id), rv.data)
                self.assertNotIn('#{0}'.format(sale2.id), rv.data)

    def test_0310_guest_user_payment_using_credit_card(self):
        """
        ===================================
        Total Sale Amount       |   $100
        Payment Authorize On:   | 'manual'
        Payment Capture On:     | 'sale_process'
        ===================================
        Total Payment Lines     |     1
        Payment 1               |   $100
        ===================================
        """
        Sale = POOL.get('sale.sale')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            app = self.get_app()

            auth_gateway = self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_guest_order(c, 10)

                sale, = Sale.search([], limit=1)

                self.assertEqual(sale.total_amount, Decimal('100'))
                self.assertEqual(sale.payment_total, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                # pay using credit card
                rv = c.post(
                    '/checkout/payment',
                    data={
                        'owner': 'Joe Blow',
                        'number': '4111111111111111',
                        'expiry_year': '2018',
                        'expiry_month': '01',
                        'cvv': '911',
                        'add_card_to_profiles': True
                    }
                )

                self.assertEqual(rv.status_code, 302)

                self.assertEqual(sale.state, 'confirmed')

                self.assertEqual(len(sale.payments), 1)

                sale_payment, = sale.payments
                self.assertEqual(sale_payment.method, auth_gateway.method)

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('100'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                with Transaction().set_context(company=self.company.id):
                    self.Sale.process([sale])
                    self.Sale.complete_payments()

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('100'))
                self.assertEqual(sale.payment_captured, Decimal('100'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

    def test_0330_registered_user_payment_using_payment_profile(self):
        """
        ===================================
        Total Sale Amount       |   $100
        Payment Authorize On:   | 'manual'
        Payment Capture On:     | 'sale_process'
        ===================================
        Total Payment Lines     |     1
        Payment 1               |   $100
        ===================================
        """
        Sale = POOL.get('sale.sale')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            app = self.get_app()

            auth_gateway = self._create_auth_net_gateway_for_site()

            with app.test_client() as c:
                self._create_regd_user_order(c, 10)

                sale, = Sale.search([], limit=1)

                self.assertEqual(sale.total_amount, Decimal('100'))
                self.assertEqual(sale.payment_total, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                gateway = self._create_auth_net_gateway_for_site()

                payment_profile = self.create_payment_profile(
                    sale.party, gateway
                )

                rv = c.post(
                    '/checkout/payment',
                    data={'payment_profile': payment_profile.id}
                )
                self.assertEqual(rv.status_code, 302)

                self.assertEqual(sale.state, 'confirmed')
                self.assertEqual(len(sale.payments), 1)

                sale_payment, = sale.payments
                self.assertEqual(sale_payment.method, auth_gateway.method)

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('100'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                with Transaction().set_context(company=self.company.id):
                    self.Sale.process([sale])
                    self.Sale.complete_payments()

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('100'))
                self.assertEqual(sale.payment_captured, Decimal('100'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

    def test_0320_registered_user_payment_using_alternate_method(self):
        """
        ===================================
        Total Sale Amount       |   $100
        Payment Authorize On:   | 'manual'
        Payment Capture On:     | 'sale_process'
        ===================================
        Total Payment Lines     |     1
        Payment 1               |   $100
        ===================================
        """
        Sale = POOL.get('sale.sale')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            app = self.get_app()

            with app.test_client() as c:
                self._create_regd_user_order(c, 10)

                sale, = Sale.search([], limit=1)

                self.assertEqual(sale.total_amount, Decimal('100'))
                self.assertEqual(sale.payment_total, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                payment_method = self._create_cheque_payment_method()

                rv = c.post(
                    '/checkout/payment',
                    data={'alternate_payment_method': payment_method.id}
                )
                self.assertEqual(rv.status_code, 302)

                self.assertEqual(sale.state, 'confirmed')

                self.assertEqual(len(sale.payments), 1)

                sale_payment, = sale.payments
                self.assertEqual(
                    sale_payment.method, payment_method.gateway.method
                )

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('100'))
                self.assertEqual(sale.payment_collected, Decimal('0'))
                self.assertEqual(sale.payment_captured, Decimal('0'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))

                with Transaction().set_context(company=self.company.id):
                    self.Sale.process([sale])
                    self.Sale.complete_payments()

                self.assertEqual(sale.payment_total, Decimal('100'))
                self.assertEqual(sale.payment_available, Decimal('0'))
                self.assertEqual(sale.payment_collected, Decimal('100'))
                self.assertEqual(sale.payment_captured, Decimal('100'))
                self.assertEqual(sale.payment_authorized, Decimal('0'))


def suite():
    "Checkout test suite"
    "Define suite"
    test_suite = trytond.tests.test_tryton.suite()
    loader = unittest.TestLoader()
    test_suite.addTests(
        loader.loadTestsFromTestCase(TestCheckoutPayment),
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
