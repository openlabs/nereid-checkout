# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Payment handling capability for Checkout

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import PoolMeta, Pool

__all__ = ['Website', 'NereidPaymentMethod']
__metaclass__ = PoolMeta


class Website:
    "Define the credit card handler"
    __name__ = 'nereid.website'

    alternate_payment_methods = fields.One2Many(
        'nereid.website.payment_method', 'website',
        'Alternate Payment Methods'
    )


class NereidPaymentMethod(ModelSQL, ModelView):
    "Alternate payment gateway mechanisms"
    __name__ = 'nereid.website.payment_method'

    name = fields.Char('Name', required=True, translate=True)
    gateway = fields.Many2One(
        'payment_gateway.gateway', 'Gateway',
        domain=[('method', '!=', 'credit_card')],
        required=True
    )
    provider = fields.Function(
        fields.Char('Provider'), 'get_provider'
    )
    method = fields.Function(
        fields.Char('Payment Gateway Method'), 'get_method'
    )
    instructions = fields.Text('Instructions')
    sequence = fields.Integer('Sequence', required=True, select=True)
    website = fields.Many2One('nereid.website', 'Website', required=True)

    @staticmethod
    def default_sequence():
        return 100

    def get_provider(self):
        """
        Return the gateway provider based on the gateway
        """
        return self.gateway.provider

    def get_method(self, name=None):
        """
        Return the method based on the gateway
        """
        return self.gateway.method

    @classmethod
    def __setup__(cls):
        super(NereidPaymentMethod, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    def process(self, transaction):
        """
        Given an amount this gateway should begin processing the payment.

        Downstream modules can subclass the model and implemented different
        payment gateway. If the payment requires the user to be redirected
        to another site, then return a HTTP response object like the one
        returned by redirect() function.

        :param transaction: Active Record of the payment transaction
        """
        PaymentTransaction = Pool().get('payment_gateway.transaction')

        if self.method == 'manual':
            return PaymentTransaction.process([transaction])

        raise Exception('Not Implemented %s' % self.method)
