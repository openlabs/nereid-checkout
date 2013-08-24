# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Nereid Checkout register and default checkout

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from nereid import render_template, request, url_for, flash, redirect, abort
from werkzeug.wrappers import BaseResponse
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta

from .i18n import _
from .forms import OneStepCheckoutRegd, OneStepCheckout

__all__ = ['Checkout', 'DefaultCheckout']
__metaclass__ = PoolMeta


class Checkout(ModelSQL, ModelView):
    "Checkout Register"
    __name__ = 'nereid.checkout'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active')
    is_allowed_for_guest = fields.Boolean('Is Allowed for Guest ?')
    model = fields.Many2One(
        'ir.model', 'Model', required=True,
        domain=[('model', 'like', 'nereid.checkout.%')]
    )


class DefaultCheckout(ModelSQL):
    'Default checkout functionality'
    __name__ = 'nereid.checkout.default'

    @classmethod
    def _begin_guest(cls):
        """Start of checkout process for guest user which is different
        from login user who may already have addresses
        """
        Cart = Pool().get('nereid.cart')

        cart = Cart.open_cart()
        form = OneStepCheckout(request.form)

        return render_template('checkout.jinja', form=form, cart=cart)

    @classmethod
    def _begin_registered(cls):
        '''Begin checkout process for registered user.'''
        Cart = Pool().get('nereid.cart')

        cart = Cart.open_cart()
        form = OneStepCheckoutRegd(request.form)
        addresses = [(0, _('New Address'))] + Cart._get_addresses()
        form.billing_address.choices = addresses
        form.shipping_address.choices = addresses

        return render_template('checkout.jinja', form=form, cart=cart)

    @classmethod
    def _process_shipment(cls, sale, form):
        """Process the shipment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.

        Add a shipping line to the sale order.

        :param sale: Browse Record of Sale Order
        :param form: Instance of validated form
        """
        pass

    @classmethod
    def _process_payment(cls, sale, form):
        """Process the payment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.


        The payment must be processed based on the following fields:

        :param sale: Active Record of Sale Order
        :param form: Instance of validated form
        """
        pass

    @classmethod
    def _handle_guest_checkout_with_regd_email(cls, email):
        """
        Handle a situation where a guest user tries to checkout but
        there is already a registered user with the email. Depending
        on your company policy you might want top do several things like
        allowing the user to checkout and also send him an email that
        you could have used the account for checkout etc.

        By default, the behavior is NOT to allow such checkouts and instead
        flash a message and quit
        """
        flash(_(
            'A registration already exists with this email. '
            'Please login or contact customer care'
        ))
        abort(redirect(url_for('nereid.checkout.default.checkout')))

    @classmethod
    def _create_address(cls, data):
        "Create a new party.address"
        Address = Pool().get('party.address')
        NereidUser = Pool().get('nereid.user')
        ContactMechanism = Pool().get('party.contact_mechanism')

        email = data.pop('email')
        phone = data.pop('phone')

        if request.is_guest_user:
            existing = NereidUser.search([
                ('email', '=', email),
                ('company', '=', request.nereid_website.company.id),
            ])
            if existing:
                cls._handle_guest_checkout_with_regd_email(email)

        data['country'] = data.pop('country')
        data['subdivision'] = data.pop('subdivision')
        data['party'] = request.nereid_user.party.id
        ContactMechanism.create([
            {
                'type': 'email',
                'party': request.nereid_user.party.id,
                'email': email,
            }, {
                'type': 'phone',
                'party': request.nereid_user.party.id,
                'value': phone,
            }
        ])
        address, = Address.create([data])
        Address.write([address], {'email': email, 'phone': phone})

        return address

    @classmethod
    def _submit_guest(cls):
        '''Submission when guest user'''
        Cart = Pool().get('nereid.cart')
        Sale = Pool().get('sale.sale')

        form = OneStepCheckout(request.form)
        cart = Cart.open_cart()
        if form.validate():
            # Get billing address
            billing_address = cls._create_address(
                form.new_billing_address.data
            )

            # Get shipping address
            shipping_address = billing_address
            if not form.shipping_same_as_billing:
                shipping_address = cls._create_address(
                    form.new_shipping_address.data
                )

            # Write the information to the order
            Sale.write(
                [cart.sale], {
                    'invoice_address': billing_address,
                    'shipment_address': shipping_address,
                }
            )
        return form, form.validate()

    @classmethod
    def _submit_registered(cls):
        '''Submission when registered user'''
        Cart = Pool().get('nereid.cart')
        Sale = Pool().get('sale.sale')

        form = OneStepCheckoutRegd(request.form)
        addresses = Cart._get_addresses()
        form.billing_address.choices.extend(addresses)
        form.shipping_address.choices.extend(addresses)

        cart = Cart.open_cart()
        if form.validate():
            # Get billing address
            if form.billing_address.data == 0:
                # New address
                billing_address = cls._create_address(
                    form.new_billing_address.data
                )
            else:
                billing_address = form.billing_address.data

            # Get shipping address
            shipping_address = billing_address
            if not form.shipping_same_as_billing:
                if form.shipping_address.data == 0:
                    shipping_address = cls._create_address(
                        form.new_shipping_address.data
                    )
                else:
                    shipping_address = form.shipping_address.data

            # Write the information to the order
            Sale.write(
                [cart.sale],
                {
                    'invoice_address': billing_address,
                    'shipment_address': shipping_address,
                }
            )

        return form, form.validate()

    @classmethod
    def checkout(cls):
        '''Submit of default checkout

        A GET to the method will result in passing of control to begin as
        that is basically the entry point to the checkout

        A POST to the method will result in the confirmation of the order and
        subsequent handling of data.
        '''
        Cart = Pool().get('nereid.cart')
        Sale = Pool().get('sale.sale')

        cart = Cart.open_cart()
        if not cart.sale:
            # This case is possible if the user changes his currency at
            # the point of checkout and the cart gets cleared.
            return redirect(url_for('nereid.cart.view_cart'))

        sale = cart.sale
        if not sale.lines:
            flash(_("Add some items to your cart before you checkout!"))
            return redirect(url_for('nereid.website.home'))
        if request.method == 'GET':
            return request.is_guest_user and cls._begin_guest() \
                or cls._begin_registered()

        elif request.method == 'POST':
            form, do_process = cls._submit_guest() if request.is_guest_user \
                else cls._submit_registered()
            if do_process:
                # Process Shipping
                cls._process_shipment(sale, form)

                # Process Payment, if the returned value from the payment
                # is a response object (isinstance) then return that instead
                # of the success page. This will allow reidrects to a third
                # party gateway or service to collect payment.
                response = cls._process_payment(sale, form)
                if isinstance(response, BaseResponse):
                    return response

                if sale.state == 'draft':
                    # Ensure that the order date is that of today
                    Cart.check_update_date(cart)
                    # Confirm the order
                    Sale.quote([sale])
                    Sale.confirm([sale])

                flash(_(
                    "Your order #%(sale)s has been processed",
                    sale=sale.reference)
                )
                if request.is_guest_user:
                    return redirect(url_for('nereid.website.home'))
                else:
                    return redirect(
                        url_for(
                            'sale.sale.render',
                            active_id=sale.id, confirmation=True
                        )
                    )

            return render_template('checkout.jinja', form=form, cart=cart)
