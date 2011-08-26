# -*- coding: utf-8 -*-
"""
    sale

    Additional Changes to sale

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import ModelSQL, ModelView, ModelWorkflow

from nereid import render_template, request, abort


class Sale(ModelWorkflow, ModelSQL, ModelView):
    """Add Render and Render list"""
    _name = 'sale.sale'

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
        if sale.party.id != request.nereid_user.party.id:
            # TODO: Check if this works for guest user
            abort(404)

        return render_template(
            'sale.jinja', sale=sale, confirmation=confirmation)

Sale()
