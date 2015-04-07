# -*- coding: utf-8 -*-
'''

    nereid_checkout

    :copyright: (c) 2010-2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool

from sale import Sale, SaleLine
from payment import Website, NereidPaymentMethod
from checkout import Cart, Checkout, Party, Address
from configuration import Configuration


def register():
    Pool.register(
        Cart,
        Sale,
        Configuration,
        Party,
        Website,
        Checkout,
        NereidPaymentMethod,
        Address,
        SaleLine,
        type_="model", module="nereid_checkout"
    )
