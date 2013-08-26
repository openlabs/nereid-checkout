# -*- coding: utf-8 -*-
'''

    nereid_checkout

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool

from sale import Sale
from checkout import Checkout, DefaultCheckout


def register():
    Pool.register(
        Sale,
        Checkout,
        DefaultCheckout,
        type_="model", module="nereid_checkout"
    )
