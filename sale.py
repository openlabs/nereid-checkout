# -*- coding: utf-8 -*-
"""
    sale

    Additional Changes to sale

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import ModelSQL, ModelView, ModelWorkflow

from nereid import render_template, request, abort, login_required


class Sale(ModelWorkflow, ModelSQL, ModelView):
    """Add Render and Render list"""
    _name = 'sale.sale'

    @login_required
    def render(self, id):
        "Render given invoice"
        sale = self.browse(id)
        if sale.party.id != request.nereid_user.party.id:
            abort(404)
        return render_template('sale-order.jinja', sale=sale)

Sale()

