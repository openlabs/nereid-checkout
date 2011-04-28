# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Nereid Checkout register and default checkout

    :copyright: (c) 2010-2011 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from nereid import render_template, request, url_for, flash, \
        redirect, login_required, abort
from werkzeug.wrappers import BaseResponse
from trytond.model import ModelView, ModelSQL, fields

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
        cart_obj = self.pool.get('nereid.cart')

        cart = cart_obj.open_cart()
        form = OneStepCheckout(request.form)

        return render_template('checkout.jinja', form=form, cart=cart)

    def _begin_registered(self):
        '''Begin checkout process for registered user.'''
        cart_obj = self.pool.get('nereid.cart')

        cart = cart_obj.open_cart()
        form = OneStepCheckoutRegd(request.form)
        addresses = [(0, 'New Address')] + cart_obj._get_addresses()
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
        address_obj = self.pool.get('party.address')
        contact_mech_obj = self.pool.get('party.contact_mechanism')

        email = data.pop('email')
        phone = data.pop('phone')

        if request.is_guest_user:
            # First search if an address with the email already exists
            # for a party who is not Guest. If it exists its not a problem
            existing_ids = contact_mech_obj.search([
                ('value', '=', email),
                ('type', '=', 'email'),
                ('party', '!=', request.nereid_user.party.id)
                ])
            if existing_ids:
                flash('A registration already exists with this email. '
                    'Please login or contact customer care')
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
        address_obj.write(address_id, {'email': email_id, 'phone': phone_id})

        return address_id

    def _submit_guest(self):
        '''Submission when guest user'''
        cart_obj = self.pool.get('nereid.cart')
        sale_obj = self.pool.get('sale.sale')

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
        cart_obj = self.pool.get('nereid.cart')
        sale_obj = self.pool.get('sale.sale')

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
        cart_obj = self.pool.get('nereid.cart')
        sale_obj = self.pool.get('sale.sale')

        cart = cart_obj.open_cart()
        if not cart.sale:
            # This case is possible if the user changes his currency at
            # the point of checkout and the cart gets cleared.
            return redirect(url_for('nereid.cart.view_cart'))

        sale = cart.sale
        if not cart.sale.lines:
            flash("Add some items to your cart before you checkout!")
            return redirect(url_for('nereid.website.home'))
        if request.method == 'GET':
            return (self._begin_guest() if request.is_guest_user \
                else self._begin_registered())

        elif request.method == 'POST':
            form, do_process = self._submit_guest() if request.is_guest_user \
                else self._submit_registered()
            if do_process:
                # Confirm the order
                sale_obj.workflow_trigger_validate([cart.sale.id], 'quotation')
                # Process Shipping
                self._process_shipment(cart.sale, form)

                # Process Payment, if the returned value from the payment
                # is a response object (isinstance) then return that instead
                # of the success page. This will allow reidrects to a third 
                # party gateway or service to collect payment.
                response = self._process_payment(cart.sale, form)
                if isinstance(response, BaseResponse):
                    return response

                sale_obj.workflow_trigger_validate([cart.sale.id], 'confirm')

                flash("Your order #%s has been processed" % sale.reference)
                if request.is_guest_user:
                    return redirect(url_for('nereid.website.home'))
                else:
                    return redirect(url_for('sale.sale.render', id=sale.id))

            return render_template('checkout.jinja', form=form, cart=cart)

DefaultCheckout()
