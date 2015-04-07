# -*- coding: utf-8 -*-
"""
    sale configuration

    :copyright: (c) 2011-2015 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""

from trytond.pool import PoolMeta

__all__ = ['Configuration']
__metaclass__ = PoolMeta


class Configuration:
    """
    Sale Configuration
    """
    __name__ = 'sale.configuration'

    @staticmethod
    def default_payment_authorize_on():
        return 'manual'

    @staticmethod
    def default_payment_capture_on():
        return 'sale_process'
