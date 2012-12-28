# -*- coding: utf-8 -*-
"""
    sale

    Additional Changes to sale

    :copyright: (c) 2011-2012 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from uuid import uuid4

from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.tools import get_smtp_server

from nereid import render_template, request, abort, login_required
from nereid.contrib.pagination import Pagination
from trytond.config import CONFIG
from nereid.templating import render_email


class Sale(Workflow, ModelSQL, ModelView):
    """Add Render and Render list"""
    _name = 'sale.sale'

    #: This access code will be cross checked if the user is guest for a match
    #: to optionally display the order to an user who has not authenticated 
    #: as yet
    guest_access_code = fields.Char('Guest Access Code')

    per_page = 10

    @login_required
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
        # This Ugly type hack is for a bug in previous versions where some
        # parts of the code passed confirmation as a text
        confirmation = False if confirmation is None else True

        sale = self.browse(sale)

        # Try to find if the user can be shown the order
        access_code = request.values.get('access_code', None)

        if request.is_guest_user:
            if not access_code:
                # No access code provided
                abort(403)
            if access_code != sale.guest_access_code:
                # Invalid access code
                abort(403)
        else:
            if sale.party.id != request.nereid_user.party.id:
                # Order does not belong to the user
                abort(403)


        return render_template(
            'sale.jinja', sale=sale, confirmation=confirmation)

    def create_guest_access_code(self, sale):
        """A guest access code must be written to the guest_access_code of the
        sale order so that it could be accessed wihtout a login

        :param sale: ID of the sale order
        """
        access_code = uuid4()
        self.write(sale, {'guest_access_code': unicode(access_code)})
        return access_code

    def send_confirmation_email(self, sale):
        """An email confirming that the order has been confirmed and that we 
        are waiting for the payment confirmation if we are really waiting for 
        it.

        For setting a convention this email has to be sent by rendering the
        templates

           * Text: `emails/sale-confirmation-text.jinja`
           * HTML: `emails/sale-confirmation-html.jinja`

        :param sale: The ID of the sale order
        """
        email_message = render_email(
            CONFIG['smtp_from'], sale.invoice_address.email,
            'Order Completed',
            text_template = 'emails/sale-confirmation-text.jinja',
            html_template = 'emails/sale-confirmation-html.jinja',
            sale = sale
        )
        server = get_smtp_server()
        server.sendmail(
            CONFIG['smtp_from'], [sale.invoice_address.email],
            email_message.as_string()
        )
        server.quit()

    def confirm(self, ids):
        "Send an email after sale is confirmed"
        super(Sale, self).confirm(ids)

        for sale in self.browse(ids):
            self.send_confirmation_email(sale)

Sale()
