# -*- coding: utf-8 -*-
"""
    __init__

    Add the test suite here so that setup.py test loader picks it up

    :copyright: © 2013-2015 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
import unittest
import trytond.tests.test_tryton
from test_checkout import TestCheckoutSignIn, TestCheckoutShippingAddress, \
    TestCheckoutDeliveryMethod, TestCheckoutBillingAddress, TestSale
from test_payment import TestCheckoutPayment
from test_address import TestAddress


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    loader = unittest.TestLoader()
    test_suite.addTests([
        loader.loadTestsFromTestCase(TestAddress),
        loader.loadTestsFromTestCase(TestCheckoutSignIn),
        loader.loadTestsFromTestCase(TestCheckoutShippingAddress),
        loader.loadTestsFromTestCase(TestCheckoutDeliveryMethod),
        loader.loadTestsFromTestCase(TestCheckoutBillingAddress),
        loader.loadTestsFromTestCase(TestCheckoutPayment),
        loader.loadTestsFromTestCase(TestSale)
    ])
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
