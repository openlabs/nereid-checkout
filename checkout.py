# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Nereid Checkout register and default checkout

    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from nereid import render_template, request, url_for, flash, redirect
from werkzeug.wrappers import BaseResponse
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool

from .i18n import _
from .forms import OneStepCheckoutRegd, OneStepCheckout

# pylint: disable-msg=E1101
# pylint: disable-msg=R0201
# pylint: disable-msg=W0232

class Checkout(ModelSQL, ModelView):
    "Checkout Register"
    _name = 'nereid.checkout'
    _description = __doc__

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active')
    is_allowed_for_guest = fields.Boolean('Is Allowed for Guest ?')
    model = fields.Many2One('ir.model', 'Model', required=True,
        domain=[('model', 'like', 'nereid.checkout.%')])

Checkout()


class DefaultCheckout(ModelSQL):
    'Default checkout functionality'
    _name = 'nereid.checkout.default'
    _description = __doc__

    def _begin_guest(self):
        """Start of checkout process for guest user which is different
        from login user who may already have addresses
        """
        cart_obj = Pool().get('nereid.cart')

        cart = cart_obj.open_cart()
        form = OneStepCheckout(request.form)

        return render_template('checkout.jinja', form=form, cart=cart)

    def _begin_registered(self):
        '''Begin checkout process for registered user.'''
        cart_obj = Pool().get('nereid.cart')

        cart = cart_obj.open_cart()
        form = OneStepCheckoutRegd(request.form)
        addresses = [(0, _('New Address'))] + cart_obj._get_addresses()
        form.billing_address.choices = addresses
        form.shipping_address.choices = addresses

        return render_template('checkout.jinja', form=form, cart=cart)

    def _process_shipment(self, sale, form):
        """Process the shipment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.

        Add a shipping line to the sale order.

        :param sale: Browse Record of Sale Order
        :param form: Instance of validated form
        """
        pass

    def _process_payment(self, sale, form):
        """Process the payment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.


        The payment must be processed based on the following fields:

        :param sale: Browse Record of Sale Order
        :param form: Instance of validated form
        """
        pass

    def _create_address(self, data):
        "Create a new party.address"
        address_obj = Pool().get('party.address')
        nereid_user_obj = Pool().get('nereid.user')
        contact_mech_obj = Pool().get('party.contact_mechanism')

        email = data.pop('email')
        phone = data.pop('phone')

        if request.is_guest_user:
            existing = nereid_user_obj.search([
                ('email', '=', email),
                ('company', '=', request.nereid_website.company.id),
                ])
            if existing:
                flash(_('A registration already exists with this email. '
                    'Please login or contact customer care'))
                return self._begin_guest()

        data['country'] = data.pop('country')
        data['subdivision'] = data.pop('subdivision')
        data['party'] = request.nereid_user.party.id
        email_id = contact_mech_obj.create({
                'type': 'email',
                'party': request.nereid_user.party.id,
                'email': email,
            })
        phone_id = contact_mech_obj.create({
                'type': 'phone',
                'party': request.nereid_user.party.id,
                'value': phone,
            })
        address_id = address_obj.create(data)
        address_obj.write(address_id, {'email': email, 'phone': phone})

        return address_id

    def _submit_guest(self):
        '''Submission when guest user'''
        cart_obj = Pool().get('nereid.cart')
        sale_obj = Pool().get('sale.sale')

        form = OneStepCheckout(request.form)
        cart = cart_obj.open_cart()
        if form.validate():
            # Get billing address
            billing_address = self._create_address(
                form.new_billing_address.data)

            # Get shipping address
            shipping_address = billing_address
            if not form.shipping_same_as_billing:
                shipping_address = self._create_address(
                    form.new_shipping_address.data)

            # Write the information to the order
            sale_obj.write(cart.sale.id, {
                'invoice_address'    : billing_address,
                'shipment_address'   : shipping_address,
                })
        return form, form.validate()

    def _submit_registered(self):
        '''Submission when registered user'''
        cart_obj = Pool().get('nereid.cart')
        sale_obj = Pool().get('sale.sale')

        form = OneStepCheckoutRegd(request.form)
        addresses = cart_obj._get_addresses()
        form.billing_address.choices.extend(addresses)
        form.shipping_address.choices.extend(addresses)

        cart = cart_obj.open_cart()
        if form.validate():
            # Get billing address
            if form.billing_address.data == 0:
                # New address
                billing_address = self._create_address(
                    form.new_billing_address.data)
            else:
                billing_address = form.billing_address.data

            # Get shipping address
            shipping_address = billing_address
            if not form.shipping_same_as_billing:
                if form.shipping_address.data == 0:
                    shipping_address = self._create_address(
                        form.new_shipping_address.data)
                else:
                    shipping_address = form.shipping_address.data

            # Write the information to the order
            sale_obj.write(cart.sale.id, {
                'invoice_address'    : billing_address,
                'shipment_address'   : shipping_address,
                })

        return form, form.validate()

    def checkout(self):
        '''Submit of default checkout

        A GET to the method will result in passing of control to begin as
        that is basically the entry point to the checkout

        A POST to the method will result in the confirmation of the order and
        subsequent handling of data.
        '''
        cart_obj = Pool().get('nereid.cart')
        sale_obj = Pool().get('sale.sale')

        cart = cart_obj.open_cart()
        if not cart.sale:
            # This case is possible if the user changes his currency at
            # the point of checkout and the cart gets cleared.
            return redirect(url_for('nereid.cart.view_cart'))

        sale = cart.sale
        if not sale.lines:
            flash(_("Add some items to your cart before you checkout!"))
            return redirect(url_for('nereid.website.home'))
        if request.method == 'GET':
            return (self._begin_guest() if request.is_guest_user \
                else self._begin_registered())

        elif request.method == 'POST':
            form, do_process = self._submit_guest() if request.is_guest_user \
                else self._submit_registered()
            if do_process:
                # Process Shipping
                self._process_shipment(sale, form)

                # Process Payment, if the returned value from the payment
                # is a response object (isinstance) then return that instead
                # of the success page. This will allow reidrects to a third 
                # party gateway or service to collect payment.
                response = self._process_payment(sale, form)
                if isinstance(response, BaseResponse):
                    return response

                if sale.state == 'draft':
                    # Ensure that the order date is that of today
                    cart_obj.check_update_date(cart)
                    # Confirm the order
                    sale_obj.quote([sale.id])
                    sale_obj.confirm([sale.id])

                flash(_("Your order #%(sale)s has been processed", sale=sale.reference))
                if request.is_guest_user:
                    return redirect(url_for('nereid.website.home'))
                else:
                    return redirect(
                        url_for(
                            'sale.sale.render', sale=sale.id, 
                            confirmation=True
                        )
                    )

            return render_template('checkout.jinja', form=form, cart=cart)

DefaultCheckout()
