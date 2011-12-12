# -*- coding: utf-8 -*-
"""
    sale

    Additional Changes to sale

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import ModelSQL, ModelView, ModelWorkflow

from nereid import render_template, request, abort, session
from nereid.helpers import Pagination


class Sale(ModelWorkflow, ModelSQL, ModelView):
    """Add Render and Render list"""
    _name = 'sale.sale'

    per_page = 10

    def render_list(self, page=1):
        """Render all orders
        """
        domain = [
            ('party', '=', request.nereid_user.party.id),
            ('state', '!=', 'draft'),
            ]

        # Handle order duration

        sales = Pagination(self, domain, page, self.per_page)
        return render_template('sales.jinja', sales=sales)

    def render(self, sale, confirmation=None):
        """Render given sale order

        :param sale: ID of the sale Order
        :param confirmation: If any value is provided for this field then this
                             page is considered the confirmation page. This
                             also passes a `True` if such an argument is proved
                             or a `False`
        """
        confirmation = False if confirmation is None else True

        sale = self.browse(sale)
        if (not request.is_guest_user) and \
                (sale.party.id != request.nereid_user.party.id):
            abort(403)
        elif request.is_guest_user and \
                (sale.invoice_address.email.value != session.get('email')):
            abort(403)

        return render_template(
            'sale.jinja', sale=sale, confirmation=confirmation)

Sale()
