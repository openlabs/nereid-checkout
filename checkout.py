# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Nereid Checkout register and default checkout

    :copyright: (c) 2010-2011 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from nereid import render_template, request, url_for, flash, \
        redirect, login_required, abort
from nereid.globals import session
from werkzeug.wrappers import BaseResponse

from trytond.model import ModelView, ModelSQL, fields

from .forms import OneStepCheckoutRegd, OneStepCheckout, CheckoutMethodForm

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


class Sale(ModelSQL):
    "Sale order"
    _name = "sale.order"

    @login_required
    def render(self, id):
        "Render the given invoice"
        sale = self.browse(id)
        if sale.party.id != request.nereid_user.party.id:
            abort(404)
        return render_template('sale-order.jinja', sale=sale)
Sale()


class DefaultCheckout(ModelSQL, ModelView):
    'Default checkout functionality'
    _name = 'nereid.checkout.default'
    _description = __doc__

    #: Begin methods: Maybe merge them into begin itself?

    def _begin_checkout(self):
        '''Begin Process confined to guest user

        A GET to this method will result in the guest checkout
        form being displayed while a POST will be considered an
        attempt to login as a registered user during checkout.

        On successful login, the current cart should be assigned
        to the user and a redirect must be issued to the checkout
        begin method itself.
        '''
        address_obj = self.pool.get('party.address')
        cart_obj = self.pool.get('nereid.cart')
        cart = cart_obj.open_cart()

        # DEPRECIATED : May be used if required.

        #checkout_method_form = CheckoutMethodForm(request.form)
        #if request.method == 'POST' and checkout_method_form.validate():
        #    result = address_obj.authenticate(
        #        checkout_method_form.username.data,
        #        checkout_method_form.password.data)
        #
        #    if result is None:
        #        flash("Invalid login credentials")
        #    else:
        #        flash("You are now logged in. Welcome %s" % result.name)
        #        session['user'] = result.id
        #        cart_obj.write_(cart.id, {'user': result.id})
        #        return redirect(url_for('callisto.checkout.default.begin'))

        #return render_template('pre-checkout.jinja',
        #    checkout_method_form=checkout_method_form, cart=cart)

        form = OneStepCheckout(request.form)
        return render_template('checkout.jinja',
            form=form, cart=cart)

    def _begin_guest(self):
        cart_obj = self.pool.get('nereid.cart')
        cart = cart_obj.open_cart()
        form = OneStepCheckout(request.form)
        return render_template('checkout.jinja',
            form=form, cart=cart)

    def _begin(self):
        'Begin checkout process for registered user'
        cart_obj = self.pool.get('nereid.cart')

        cart = cart_obj.open_cart()
        form = OneStepCheckoutRegd(request.form)
        addresses = [(0, 'New Address')] + cart_obj._get_addresses()
        form.billing_address.choices = addresses
        form.shipping_address.choices = addresses
        return render_template('checkout.jinja', form=form, cart=cart)

    def begin(self):
        '''Checks whether the cart has something in it or not.
        Then checks whether the user is guest or not and then proceed
        accordingly'''
        cart_obj = self.pool.get('nereid.cart')
        cart = cart_obj.open_cart()
        if not cart.sale.lines:
            flash("Add some items to the cart before checkout")
            return redirect(url_for('product.category.render_list'))
        'Entry point to checkout process'
        if request.is_guest_user:
            return self._begin_checkout()
        return self._begin()

    def save_billing_address(self):
        '''If a billing address is entered by the user, then
        it is saved here. 

        The possible options are:

        1. Guest user:
            (a.) A form with just address is given
        2. Regsitered user:
            (a.) Chose to use an exsiting address
            (b.) Chose to fill up a new address form

        Ensure that only POST method is allowed. If the request is not
        XHR, then an InternalServerError is raised

        TODO
        '''
        pass

    def _process_shipment(self, request):
        """Process the shipment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.

        Add a shipping line to the sale order.
        """
        pass

    def _process_payment(self):
        """Process the payment

        It is assumed that the form is validated before control
        passes here. Hence no extra validations are performed and
        the form fields are accessed directly.


        The payment must be processed based on the following fields
        """
        pass

    def _order_workflow_validate(self, signal):
        """Trigger a signal in the workflow of order related to cart

        This is a helper method to avoid recoding everytime a workflow
        trigger has to be made. The remaining arguments required for
        :func:`trg_validate` are automatically sent.

        :param signal: The name of signal to invoke a transition
        """
        cart_obj = self.pool.get('nereid.cart')
        sale_obj = self.pool.get('sale.sale')
        cart = cart_obj.open_cart()

        return sale_obj.workflow_trigger_validate(cart.sale.id, signal)

    def _create_address(self, data):
        "Create or write to a new party.address"
        address_obj = self.pool.get('party.address')
        contact_mech_obj = self.pool.get('party.contact_mechanism')
        data['country'] = data.pop('country')
        data['subdivision'] = data.pop('subdivision')
        data['party'] = request.nereid_user.party.id
        email = data.pop('email')
        phone = data.pop('phone')
        # First search if an address with the email already exists
        existing = contact_mech_obj.search([
            ('value', '=', email),
            ('type', '=', 'email')])
        if request.is_guest_user:
            if existing:
                flash('A registration already exists with this email. '
                    'Please login or contact customer care')
                return redirect(url_for('nereid.website.login'))
            email_id = contact_mech_obj.create({
                    'type': 'email',
                    'party': request.nereid_user.party.id,
                    'email': email,
                })
        else:
            email_id = request.nereid_user.email
        phone_id = contact_mech_obj.create({
                'type': 'phone',
                'party': request.nereid_user.party.id,
                'email': phone,
            })
        address_id = address_obj.create(data)
        address_obj.write(address_id, 
            {'email': email_id, 'phone': phone_id})
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

    def _submit(self):
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

    def submit(self):
        '''Submit of default checkout
        Allow only POST to this method
        '''
        cart_obj = self.pool.get('nereid.cart')
        form, process = self._submit_guest() if request.is_guest_user \
            else self._submit()
        cart = cart_obj.open_cart()

        if process:
            # Confirm the order
            self._order_workflow_validate('quotation')
            #self._order_workflow_validate('confirm')            
            sale = cart.sale

            # Process Shipping
            self._process_shipment(request)

            # Process Payment, if the returned value from the payment
            # is a response object (isinstance) then return that instead
            # of the success page. This will allow reidrects to a third 
            # party gateway or service to collect payment.
            response = self._process_payment()
            if isinstance(response, BaseResponse):
                return response

            flash("Your order #%s has been successfully processed" % sale.id)
            if request.is_guest_user:
                return redirect(url_for('nereid.website.home'))
            else:
                return redirect(url_for('sale.sale.render', id=sale.id))
        return render_template('checkout.jinja', form=form, cart=cart)
        
    def checkout(self):
        """On method="GET" redirect to begin checkout
            On method="POST" redirect to submit
        """
        if request.method == 'GET':
            return self.begin()
        elif request.method == 'POST':
            return self.submit()

DefaultCheckout()
