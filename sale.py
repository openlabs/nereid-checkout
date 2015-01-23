# -*- coding: utf-8 -*-
"""
    sale

    Additional Changes to sale

    :copyright: (c) 2011-2015 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
import json
from uuid import uuid4
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from trytond.model import fields
from trytond.pool import PoolMeta, Pool

from nereid import render_template, request, abort, login_required, \
    route, current_user, flash, redirect, url_for, jsonify
from nereid.contrib.pagination import Pagination
from nereid.ctx import has_request_context
from trytond.transaction import Transaction

from .i18n import _

__all__ = ['Sale', 'SaleLine']
__metaclass__ = PoolMeta


class Sale:
    """Add Render and Render list"""
    __name__ = 'sale.sale'

    #: This access code will be cross checked if the user is guest for a match
    #: to optionally display the order to an user who has not authenticated
    #: as yet
    guest_access_code = fields.Char('Guest Access Code')

    per_page = 10

    @staticmethod
    def default_guest_access_code():
        """A guest access code must be written to the guest_access_code of the
        sale order so that it could be accessed without a login
        """
        return unicode(uuid4())

    @classmethod
    @route('/orders')
    @route('/orders/<int:page>')
    @login_required
    def render_list(cls, page=1):
        """Render all orders
        """
        filter_by = request.args.get('filter_by', None)

        domain = [
            ('party', '=', request.nereid_user.party.id),
        ]
        req_date = (
            date.today() + relativedelta(months=-3)
        )

        if filter_by == 'done':
            domain.append(('state', '=', 'done'))

        elif filter_by == 'canceled':
            domain.append(('state', '=', 'cancel'))

        elif filter_by == 'archived':
            domain.append(
                ('state', 'not in', ('draft', 'quotation'))
            )

            # Add a sale_date domain for recent orders.
            domain.append((
                'sale_date', '<', req_date
            ))

        else:
            domain.append(('state', 'not in', ('draft', 'quotation', 'cancel')))

            # Add a sale_date domain for recent orders.
            domain.append((
                'sale_date', '>=', req_date
            ))

        # Handle order duration
        sales = Pagination(cls, domain, page, cls.per_page)

        return render_template('sales.jinja', sales=sales)

    @route('/order/<int:active_id>')
    @route('/order/<int:active_id>/<confirmation>')
    def render(self, confirmation=None):
        """Render given sale order

        :param sale: ID of the sale Order
        :param confirmation: If any value is provided for this field then this
                             page is considered the confirmation page. This
                             also passes a `True` if such an argument is proved
                             or a `False`
        """
        NereidUser = Pool().get('nereid.user')

        # This Ugly type hack is for a bug in previous versions where some
        # parts of the code passed confirmation as a text
        confirmation = False if confirmation is None else True

        # Try to find if the user can be shown the order
        access_code = request.values.get('access_code', None)

        if current_user.is_anonymous():
            if not access_code:
                # No access code provided, user is not authorized to
                # access order page
                return NereidUser.unauthorized_handler()
            if access_code != self.guest_access_code:
                # Invalid access code
                abort(403)
        else:
            if self.party.id != request.nereid_user.party.id:
                # Order does not belong to the user
                abort(403)

        return render_template(
            'sale.jinja', sale=self, confirmation=confirmation
        )

    @classmethod
    def confirm(cls, sales):
        "Send an email after sale is confirmed"
        super(Sale, cls).confirm(sales)

        if has_request_context():
            for sale in sales:

                # Change party name to invoice address name for guest user
                if current_user.is_anonymous():
                    sale.party.name = sale.invoice_address.name
                    sale.party.save()

    def nereid_pay_using_credit_card(self, credit_card_form, amount):
        '''
        Complete using the given card.

        If the user is registered and the save card option is given, then
        first save the card and delegate to :meth:`_complete_using_profile`
        with the profile thus obtained.

        Otherwise a payment transaction is created with the given card data.
        '''
        AddPaymentProfileWizard = Pool().get(
            'party.party.payment_profile.add', type='wizard'
        )

        gateway = request.nereid_website.credit_card_gateway

        if not current_user.is_anonymous() and \
                credit_card_form.add_card_to_profiles.data and \
                request.nereid_website.save_payment_profile:
            profile_wiz = AddPaymentProfileWizard(
                AddPaymentProfileWizard.create()[0]     # Wizard session
            )

            profile_wiz.card_info.party = self.party
            profile_wiz.card_info.address = self.invoice_address
            profile_wiz.card_info.provider = gateway.provider
            profile_wiz.card_info.gateway = gateway
            profile_wiz.card_info.owner = credit_card_form.owner.data
            profile_wiz.card_info.number = credit_card_form.number.data
            profile_wiz.card_info.expiry_month = \
                credit_card_form.expiry_month.data
            profile_wiz.card_info.expiry_year = \
                unicode(credit_card_form.expiry_year.data)
            profile_wiz.card_info.csc = credit_card_form.cvv.data

            with Transaction().set_context(return_profile=True):
                profile = profile_wiz.transition_add()
                return self.nereid_pay_using_profile(
                    profile.id, amount
                )

        return self._pay_using_credit_card(
            gateway, {
                'owner': credit_card_form.owner.data,
                'number': credit_card_form.number.data,
                'expiry_month': credit_card_form.expiry_month.data,
                'expiry_year': unicode(credit_card_form.expiry_year.data),
                'cvv': credit_card_form.cvv.data,
            },
            amount
        )

    def nereid_pay_using_alternate_payment_method(self, payment_form, amount):
        '''
        :param payment_form: The validated payment_form to extract additional
                             info
        '''
        PaymentTransaction = Pool().get('payment_gateway.transaction')
        PaymentMethod = Pool().get('nereid.website.payment_method')

        payment_method = PaymentMethod(
            payment_form.alternate_payment_method.data
        )

        payment_transaction = PaymentTransaction(
            party=self.party,
            address=self.invoice_address,
            amount=amount,
            currency=self.currency,
            gateway=payment_method.gateway,
            sale=self,
        )
        payment_transaction.save()

        return payment_method.process(payment_transaction)

    def nereid_pay_using_profile(self, payment_profile_id, amount):
        """
        Pay the amount using the given profile. Ensures that the profile
        belongs to the current user.
        """
        PaymentProfile = Pool().get('party.payment_profile')

        payment_profile = PaymentProfile(payment_profile_id)
        if payment_profile.party != current_user.party:
            # verify that the payment profile belongs to the registered
            # user.
            flash(_('The payment profile chosen is invalid'))
            return redirect(
                url_for('nereid.checkout.payment_method')
            )
        return self._pay_using_profile(payment_profile, amount)

    @route('/order/<int:active_id>/add-comment', methods=['POST'])
    def add_comment_to_sale(self):
        """
        Add comment to sale.

        User can add comment or note to sale order.
        """
        comment_is_allowed = False

        if self.state not in ['confirmed', 'processing']:
            abort(403)

        if current_user.is_anonymous():
            access_code = request.values.get('access_code', None)
            if access_code and access_code == self.guest_access_code:
                # No access code provided
                comment_is_allowed = True

        elif current_user.is_authenticated() and \
                current_user.party == self.party:
            comment_is_allowed = True

        if not comment_is_allowed:
            abort(403)

        if request.form.get('comment') and not self.comment \
                and self.state == 'confirmed':
            self.comment = request.form.get('comment')
            self.save()
            if request.is_xhr:
                return jsonify({
                    'message': 'Comment Added',
                    'comment': self.comment,
                })

            flash(_('Comment Added'))
        return redirect(request.referrer)

    def _get_amount_to_checkout(self):
        """
        Returns the amount which needs to be paid

        Downstream modules can override this method to change it as
        per their requirement
        """
        return self.amount_to_receive

    def _get_email_template_context(self):
        """
        Update context
        """
        context = super(Sale, self)._get_email_template_context()

        if has_request_context() and not current_user.is_anonymous():
            customer_name = current_user.display_name
        else:
            customer_name = self.party.name

        context.update({
            'url_for': lambda *args, **kargs: url_for(*args, **kargs),
            'has_request_context': lambda *args, **kargs: has_request_context(
                *args, **kargs),
            'current_user': current_user,
            'customer_name': customer_name,
            'to_json': lambda *args, **kargs: json.dumps(*args, **kargs),
        })
        return context

    def _get_receiver_email_address(self):
        """
        Update reciever's email address(s)
        """
        to_emails = set()
        if self.party.email:
            to_emails.add(self.party.email.lower())
        if has_request_context() and not current_user.is_anonymous() and \
                current_user.email:
            to_emails.add(current_user.email.lower())

        return list(to_emails)

    def as_json_ld(self):
        """
        Gmail markup for order information

        https://developers.google.com/gmail/markup/reference/order
        """
        data = {
            "@context": "http://schema.org",
            "@type": "Order",
            "customer": {
                "@type": "Person",
                "name": self.party.name,
            },
            "merchant": {
                "@type": "Organization",
                "name": self.company.rec_name
            },
            "orderNumber": self.reference,
            "orderDate": str(
                datetime.combine(self.sale_date, datetime.min.time())
            ),
            "orderStatus": "http://schema.org/OrderStatus/OrderProcessing",
            "priceCurrency": self.currency.code,
            "price": str(self.total_amount),
            "acceptedOffer": [],
            "url": url_for(
                'sale.sale.render', active_id=self.id,
                access_code=self.guest_access_code, _external=True
            )
        }

        for line in self.lines:
            if not line.type == 'line' and not line.product:
                continue
            data["acceptedOffer"].append(line.as_json_ld())

        if self.invoice_address:
            data["billingAddress"] = {
                "@type": "PostalAddress",
                "name": self.invoice_address.name or self.party.name,
                "streetAddress": self.invoice_address.street,
                "addressLocality": self.invoice_address.city,
                "addressRegion": self.invoice_address.subdivision and self.invoice_address.subdivision.rec_name,  # noqa
                "addressCountry": self.invoice_address.country and self.invoice_address.country.rec_name  # noqa
            }
        return data


class SaleLine:
    __name__ = 'sale.line'

    def as_json_ld(self):
        """
        Gmail markup for order line information

        https://developers.google.com/gmail/markup/reference/order
        """
        return {
            "@type": "Offer",
            "itemOffered": {
                "@type": "Product",
                "name": self.product.name,
                "sku": self.product.code,
                "url": url_for(
                    'product.product.render',
                    uri=self.product.uri,
                    _external=True
                ) if self.product.uri else None
            },
            "price": str(self.amount),
            "priceCurrency": self.sale.currency.code,
            "eligibleQuantity": {
                "@type": "QuantitativeValue",
                "value": self.quantity,
            }
        }
