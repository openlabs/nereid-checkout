# -*- coding: utf-8 -*-
'''

    nereid_checkout test address

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import unittest
import pycountry
import datetime
from dateutil.relativedelta import relativedelta

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.transaction import Transaction

from nereid.testing import NereidTestCase


class TestAddress(NereidTestCase):
    """
    Test Address
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_checkout')

        self.nereid_website_obj = POOL.get('nereid.website')
        self.nereid_website_locale_obj = POOL.get('nereid.website.locale')
        self.nereid_user_obj = POOL.get('nereid.user')
        self.company_obj = POOL.get('company.company')
        self.currency_obj = POOL.get('currency.currency')
        self.language_obj = POOL.get('ir.lang')
        self.country_obj = POOL.get('country.country')
        self.subdivision_obj = POOL.get('country.subdivision')
        self.party_obj = POOL.get('party.party')
        self.address_obj = POOL.get('party.address')
        self.contact_mech_obj = POOL.get('party.contact_mechanism')
        self.SaleChannel = POOL.get('sale.channel')
        self.PriceList = POOL.get('product.price_list')
        self.StockLocation = POOL.get('stock.location')
        self.PaymentTerm = POOL.get('account.invoice.payment_term')
        self.User = POOL.get('res.user')

        self.templates = {
            'address-edit.jinja':
            'Address Edit {% if address %}ID:{{ address.id }}{% endif %}'
            '{{ form.errors }}',
            'address.jinja': '',
        }

    def create_countries(self, count=5):
        """
        Create some sample countries and subdivisions
        """
        for country in list(pycountry.countries)[0:count]:
            country_id, = self.country_obj.create([{
                'name': country.name,
                'code': country.alpha2,
            }])
            try:
                divisions = pycountry.subdivisions.get(
                    country_code=country.alpha2
                )
            except KeyError:
                pass
            else:
                self.subdivision_obj.create([{
                    'country': country_id,
                    'name': subdivision.name,
                    'code': subdivision.code,
                    'type': subdivision.type.lower(),
                } for subdivision in list(divisions)[0:count]])

    def _create_fiscal_year(self, date=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date is None:
            date = datetime.date.today()

        if company is None:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date.year,
            'code': 'account.invoice',
            'company': company,
            'prefix': 'ab',
            'suffix': 'op',
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else False

    def setup_defaults(self):
        """
        Setup the defaults
        """
        usd, = self.currency_obj.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])
        with Transaction().set_context(company=None):
            self.party, = self.party_obj.create([{
                'name': 'Openlabs',
                'addresses': [('create', [{
                    'name': 'Openlabs',
                }])],
            }])
        self.company, = self.company_obj.create([{
            'party': self.party,
            'currency': usd,
        }])
        self.User.write([self.User(USER)], {
            'company': self.company,
            'main_company': self.company,
        })
        # Create Fiscal Year
        self._create_fiscal_year(company=self.company.id)
        # Create Chart of Accounts
        self._create_coa_minimal(company=self.company.id)

        party, = self.party_obj.create([{
            'name': 'Registered User',
        }])
        self.registered_user, = self.nereid_user_obj.create([{
            'party': party,
            'display_name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': self.company,
        }])
        self.guest_user, = self.nereid_user_obj.create([{
            'party': party,
            'display_name': 'Guest User',
            'company': self.company,
        }])

        self.create_countries()
        self.available_countries = self.country_obj.search([], limit=5)

        en_us, = self.language_obj.search([('code', '=', 'en_US')])
        currency, = self.currency_obj.search([('code', '=', 'USD')])
        locale, = self.nereid_website_locale_obj.create([{
            'code': 'en_US',
            'language': en_us,
            'currency': currency,
        }])
        # Create Sale Shop
        self.price_list, = self.PriceList.create([{
            'name': 'Test Price List',
            'company': self.company.id,
        }])
        self.payment_term, = self.PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

        with Transaction().set_context(company=self.company.id):
            self.channel, = self.SaleChannel.create([{
                'name': 'Default Channel',
                'price_list': self.price_list,
                'invoice_method': 'order',
                'shipment_method': 'order',
                'source': 'manual',
                'create_users': [('add', [USER])],
                'warehouse': self.StockLocation.search([
                         ('type', '=', 'warehouse')
                     ])[0],
                'payment_term': self.payment_term,
                'company': self.company.id,
            }])

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id,
                'current_channel': self.channel,
            }
        )

        self.nereid_website_obj.create([{
            'name': 'localhost',
            'application_user': USER,
            'channel': self.channel,
            'company': self.company,
            'default_locale': locale,
            'locales': [('add', [locale.id])],
            'countries': [('add', self.available_countries)],
            'guest_user': self.guest_user,
        }])

    def get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

    def test_0010_add_address(self):
        """
        Add an address for the user.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            registered_user = self.registered_user

            address_data = {
                'name': 'Name',
                'street': 'Street',
                'streetbis': 'StreetBis',
                'zip': 'zip',
                'city': 'City',
                'phone': '1234567890',
                'country': self.available_countries[0].id,
                'subdivision': self.country_obj(
                    self.available_countries[0]).subdivisions[0].id,
            }

            with app.test_client() as c:
                response = c.post(
                    '/en_US/login',
                    data={
                        'email': 'email@example.com',
                        'password': 'password',
                    }
                )
                self.assertEqual(response.status_code, 302)  # Login success

                self.assertEqual(len(registered_user.party.addresses), 0)

                # POST and a new address must be created
                response = c.post('/en_US/create-address', data=address_data)
                self.assertEqual(response.status_code, 302)

                # Re browse the record
                registered_user = self.nereid_user_obj(
                    self.registered_user.id
                )
                # Check if the user has one address now
                self.assertEqual(len(registered_user.party.addresses), 1)

                address, = registered_user.party.addresses
                self.assertEqual(address.name, address_data['name'])
                self.assertEqual(address.street, address_data['street'])
                self.assertEqual(address.streetbis, address_data['streetbis'])
                self.assertEqual(address.zip, address_data['zip'])
                self.assertEqual(address.city, address_data['city'])
                self.assertEqual(
                    address.phone_number.value, address_data['phone']
                )
                self.assertEqual(address.country.id, address_data['country'])
                self.assertEqual(
                    address.subdivision.id, address_data['subdivision']
                )

    def test_0020_edit_address(self):
        """
        Edit an address for the user
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            registered_user = self.registered_user
            address_data = {
                'name': 'Name',
                'street': 'Street',
                'streetbis': 'StreetBis',
                'zip': 'zip',
                'city': 'City',
                'phone': '1234567890',
                'country': self.available_countries[0].id,
                'subdivision': self.country_obj(
                        self.available_countries[0]).subdivisions[0].id,
            }

            with app.test_client() as c:
                response = c.post(
                    '/en_US/login',
                    data={
                        'email': 'email@example.com',
                        'password': 'password',
                    }
                )
                self.assertEqual(response.status_code, 302)  # Login success

                # Create an address that can be edited
                self.assertEqual(len(registered_user.party.addresses), 0)
                existing_address, = self.address_obj.create([{
                    'party': registered_user.party.id,
                }])

                response = c.get(
                    '/en_US/edit-address/%d' % existing_address.id
                )
                self.assertTrue('ID:%s' % existing_address.id in response.data)

                # POST to the existing address must updatethe existing address
                response = c.post(
                    '/en_US/edit-address/%d' % existing_address.id,
                    data=address_data
                )
                self.assertEqual(response.status_code, 302)

                # Assert that the user has only 1 address
                self.assertEqual(len(registered_user.party.addresses), 1)

                address = self.address_obj(existing_address.id)
                self.assertEqual(address.name, address_data['name'])
                self.assertEqual(address.street, address_data['street'])
                self.assertEqual(address.streetbis, address_data['streetbis'])
                self.assertEqual(address.zip, address_data['zip'])
                self.assertEqual(address.city, address_data['city'])
                self.assertEqual(
                    address.phone_number.value, address_data['phone']
                )
                self.assertEqual(address.country.id, address_data['country'])
                self.assertEqual(
                    address.subdivision.id, address_data['subdivision']
                )


def suite():
    "Test Address"
    test_suite = trytond.tests.test_tryton.suite()
    loader = unittest.TestLoader()
    test_suite.addTests(
        loader.loadTestsFromTestCase(TestAddress),
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
