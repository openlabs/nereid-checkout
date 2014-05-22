# -*- coding: utf-8 -*-
"""
    nereid-checkout

    Nereid Checkout register and default checkout

    :copyright: (c) 2010-2014 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from datetime import datetime
from functools import wraps

from nereid import render_template, request, url_for, flash, redirect, \
    current_app, current_user, route
from nereid.signals import failed_login
from nereid.globals import session
from flask.ext.login import login_user, login_fresh
from flask_wtf import Form
from wtforms import TextField, RadioField, validators, PasswordField, \
    ValidationError, SelectField, BooleanField
from werkzeug.wrappers import BaseResponse
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

from .i18n import _

__all__ = ['Cart', 'Party', 'Checkout', 'Party']
__metaclass__ = PoolMeta


class Cart:
    __name__ = 'nereid.cart'

    def get_alternate_payment_methods(self):
        """
        Get possible payment methods for this cart.

        The default implementation returns all the possible payment methods
        that exist in the website.

        Downstream modules can additional filters to decide which payment
        methods are available. For example, to limit COD below certain amount.
        """
        return self.website.alternate_payment_methods


def not_empty_cart(function):
    """
    Ensure that the shopping cart of the current session is not empty. If it is
    redirect to the shopping cart page.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        NereidCart = Pool().get('nereid.cart')
        cart = NereidCart.open_cart()
        if not (cart.sale and cart.sale.lines):
            current_app.logger.debug(
                'No sale or lines. Redirect to shopping-cart'
            )
            return redirect(url_for('nereid.cart.view_cart'))
        return function(*args, **kwargs)
    return wrapper


def recent_signin(function):
    """
    Ensure that the session for the registered user is recent.

    The functionality is similar to fresh_login_required provided by
    Flask-Login expect that the check is done only when a registered user
    tries to checkout.

    The guest user does not require to have a recent signin check

    :meth:`Checkout.is_recent_signin` method.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not current_user.is_anonymous():
            # Check only for logged in users. Guest checkouts are always
            # fresh ;-)
            if not login_fresh():
                current_app.logger.debug(
                    'No recent sign-in. Redirect to sign-in'
                )
                return redirect(url_for('nereid.checkout.sign_in'))
        return function(*args, **kwargs)
    return wrapper


def sale_has_non_guest_party(function):
    """
    Ensure that the sale has a party who is not guest.

    The sign-in method authomatically changes the party to a party based on the
    session.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        NereidCart = Pool().get('nereid.cart')
        cart = NereidCart.open_cart()
        if cart.sale and \
                cart.sale.party == request.nereid_website.guest_user.party:
            # The cart is owned by the guest user party
            current_app.logger.debug(
                'Cart is owned by guest. Redirect to sign-in'
            )
            return redirect(url_for('nereid.checkout.sign_in'))
        return function(*args, **kwargs)
    return wrapper


def with_company_context(function):
    '''
    Executes the function within the context of the website company
    '''
    @wraps(function)
    def wrapper(*args, **kwargs):
        with Transaction().set_context(
                company=request.nereid_website.company.id):
            return function(*args, **kwargs)
    return wrapper


class Party:
    __name__ = 'party.party'

    # The nereid session which created the party. This is used for
    # vaccuming parties which dont need to exist, since they have only
    # carts abandoned for a long time
    nereid_session = fields.Char('Nereid Session')

    def get_payment_profiles(self, method='credit_card'):
        '''
        Return all the payment profiles of the type
        '''
        PaymentProfile = Pool().get('party.payment_profile')

        return PaymentProfile.search([
            ('party', '=', self.id),
            ('gateway.method', '=', method),
        ])


class CreditCardForm(Form):
    owner = TextField('Full Name on Card', [validators.Required(), ])
    number = TextField(
        'Card Number', [validators.Required(), validators.Length(max=20)]
    )
    expiry_month = SelectField(
        'Card Expiry Month',
        [validators.Required(), validators.Length(min=2, max=2)],
        choices=[
            ('01', _('01-January')),
            ('02', _('02-February')),
            ('03', _('03-March')),
            ('04', _('04-April')),
            ('05', _('05-May')),
            ('06', _('06-June')),
            ('07', _('07-July')),
            ('08', _('08-August')),
            ('09', _('09-September')),
            ('10', _('10-October')),
            ('11', _('11-November')),
            ('12', _('12-December')),
        ]
    )

    current_year = datetime.utcnow().date().year
    year_range = (current_year, current_year + 25)
    expiry_year = SelectField(
        'Card Expiry Year',
        [validators.Required(), validators.NumberRange(*year_range)],
        coerce=int,
    )
    cvv = TextField(
        'CVD/CVV Number',
        [validators.Required(), validators.Length(min=3, max=4)]
    )
    add_card_to_profiles = BooleanField('Save Card')

    def __init__(self, *args, **kwargs):
        super(CreditCardForm, self).__init__(*args, **kwargs)

        # Set the expiry year values
        self.expiry_year.choices = [
            (year, year) for year in range(*self.year_range)
        ]


class PaymentForm(Form):
    'Form to capture additional payment data'
    use_shipment_address = BooleanField(
        _('Use shipping address as billing address')
    )
    payment_profile = SelectField(
        _('Choose a card'),
        [validators.Optional()],
        choices=[], coerce=int
    )
    alternate_payment_method = SelectField(
        _('Alternate payment methods'),
        [validators.Optional()],
        choices=[], coerce=int
    )


class CheckoutSignInForm(Form):
    "Checkout Sign-In Form"
    email = TextField(_('e-mail'), [validators.Required(), validators.Email()])
    password = PasswordField(_('Password'))
    checkout_mode = RadioField(
        'Checkout Mode', choices=[
            ('guest', _('Checkout as a guest')),
            ('account', _('Use my account')),
        ]
    )
    remember = BooleanField(_('Remember Me'))

    def validate_password(self, field):
        if self.checkout_mode.data == 'account' and not field.data:
            raise ValidationError(_('Password is required.'))


class Checkout(ModelView):
    'A checkout model'
    __name__ = 'nereid.checkout'

    @classmethod
    @route('/checkout/sign-in', methods=['GET', 'POST'])
    @not_empty_cart
    def sign_in(cls):
        '''
        Step 1: Sign In or Register

        GET
        ~~~

        Renders a sign-in or register page. If guest checkout is enabled, then
        an option to continue as guest is also permitted, in which case the
        email is a required field.

        POST
        ~~~~

        For guest checkout, this sign in would create a new party with the name
        as the current session_id and move the shopping cart's sale to the
        new user's ownership

        Designer notes: The registration or login must contact the
        corresponding handlers. Login and Registraion handlers are designed to
        handle a `next` parameter where the user would be redirected to if the
        operation was successful. The next url is provided in the context

        OTOH, if the user desires to checkout as guest, the user is required to
        fill in the email and submit the form, which posts the email to this
        handler.
        '''
        NereidCart = Pool().get('nereid.cart')
        NereidUser = Pool().get('nereid.user')
        Party = Pool().get('party.party')

        if not request.is_guest_user:
            form = CheckoutSignInForm(
                email=current_user.email,
                checkout_mode='account',
            )
        else:
            # Guest user
            form = CheckoutSignInForm(
                email=session.get('email'),
                checkout_mode='guest',
            )

        if form.validate_on_submit():
            if form.checkout_mode.data == 'guest':
                existing = NereidUser.search([
                    ('email', '=', form.email.data),
                    ('company', '=', request.nereid_website.company.id),
                ])
                if existing:
                    return render_template(
                        'checkout/signin-email-in-use.jinja',
                        email=form.email.data
                    )

                cart = NereidCart.open_cart()
                party_name = unicode(_(
                    'Guest with email: %(email)s', email=form.email.data
                ))
                if cart.sale.party == request.nereid_website.guest_user.party:
                    # Create a party with the email as email, and session as
                    # name, but attach the session to it.
                    party, = Party.create([{
                        'name': party_name,
                        'nereid_session': session.sid,
                        'addresses': [],
                        'contact_mechanisms': [('create', [{
                            'type': 'email',
                            'value': form.email.data,
                        }])]
                    }])

                    cart.sale.party = party
                    # TODO: Avoid this if the user comes to sign-in twice.
                    cart.sale.shipment_address = None
                    cart.sale.invoice_address = None
                    cart.sale.save()
                else:
                    # Perhaps the email changed ?
                    party = cart.sale.party
                    party.name = party_name

                    # contact_mechanism of email type will always be there for
                    # Guest user
                    contact_mechanism = filter(
                        lambda c: c.type == 'email', party.contact_mechanisms
                    )[0]
                    contact_mechanism.value = form.email.data
                    contact_mechanism.save()
                    party.email = form.email.data
                    party.save()

                return redirect(
                    url_for('nereid.checkout.shipping_address')
                )
            else:
                # The user wants to use existing email to login
                user = NereidUser.authenticate(
                    form.email.data, form.password.data
                )
                if user:
                    # FIXME: Remove remember_me
                    login_user(user, remember=form.remember.data)
                    return redirect(
                        url_for('nereid.checkout.shipping_address')
                    )
                else:
                    failed_login.send()

        if not current_user.is_anonymous() and login_fresh():
            # Registered user with a fresh login can directly proceed to
            # step 2, which is filling the shipping address
            #
            # if this is a recent sign-in by a registred user
            # automatically proceed to the shipping_address step
            return redirect(url_for('nereid.checkout.shipping_address'))

        return render_template(
            'checkout/signin.jinja',
            form=form,
            next=url_for('nereid.checkout.shipping_address')
        )

    @classmethod
    def get_new_address_form(cls, address=None):
        '''
        Returns a WTForm class which should be used for form validation when a
        new address is created as part of shipping or billing address during
        checkout.

        This is separately maintained to make it easier for customisation.

        By default the form returned is the same form as that of NereidUser
        registration.

        :param address: The address from which to fill data
        '''
        Address = Pool().get('party.address')
        return Address.get_address_form(address)

    @classmethod
    @route('/checkout/shipping-address', methods=['GET', 'POST'])
    @recent_signin
    @not_empty_cart
    @sale_has_non_guest_party
    def shipping_address(cls):
        '''
        Choose or Create a shipping address

        Guest users are only allowed to create a new address while registered
        users are allowed to either choose an address or create a new one.

        GET
        ~~~

        Renders the shipping_address selection/creation page.

        The template context would have an addresses variable which carries a
        list of addresses in the case of registered users. For guest users the
        variable would be empty.

        POST
        ~~~~

        **Registered User**: If `address` (the id of the chosen address) is in
        the POST values, then the address is validated and stored as the
        `shipment_address` in the sale. If not, the new address form is
        validated to see if a new address has to be created for the party.

        **Guest User**: New address data has to be provided and validated to
        create the new address.

        Once the address is set succesfully, the delivery_options page is shown
        '''
        NereidCart = Pool().get('nereid.cart')
        Address = Pool().get('party.address')

        cart = NereidCart.open_cart()
        address_form = cls.get_new_address_form(cart.sale.shipment_address)

        if request.method == 'POST':
            if not request.is_guest_user and request.form.get('address'):
                # Registered user has chosen an existing address
                address = Address(request.form.get('address', type=int))

                if address.party != cart.sale.party:
                    flash(_('The address chosen is not valid'))
                    return redirect(
                        url_for('nereid.checkout.shipping_address')
                    )

            else:
                # Guest user or registered user creating an address. Only
                # difference is that the party of address depends on guest or
                # not
                if not address_form.validate():
                    address = None
                else:
                    if request.is_guest_user and cart.sale.shipment_address:
                        # Save to the same address if the guest user
                        # is just trying to update the address
                        address = cart.sale.shipment_address
                    else:
                        address = Address()

                    address.party = cart.sale.party
                    address.name = address_form.name.data
                    address.street = address_form.street.data
                    address.streetbis = address_form.streetbis.data
                    address.zip = address_form.zip.data
                    address.city = address_form.city.data
                    address.country = address_form.country.data
                    address.subdivision = address_form.subdivision.data
                    address.save()

            if address is not None:
                # Finally save the address to the shipment
                cart.sale.shipment_address = address
                cart.sale.save()

                return redirect(
                    url_for('nereid.checkout.delivery_method')
                )

        addresses = []
        if not request.is_guest_user:
            addresses.extend(current_user.party.addresses)

        return render_template(
            'checkout/shipping_address.jinja',
            addresses=addresses,
            address_form=address_form,
        )

    @classmethod
    @route('/checkout/delivery-method', methods=['GET', 'POST'])
    @not_empty_cart
    @recent_signin
    @sale_has_non_guest_party
    def delivery_method(cls):
        '''
        Selection of delivery method (options)

        Based on the shipping address selected, the delivery options
        could be shown to the user. This may include choosing shipping speed
        and if there are multiple items, the option to choose items as they are
        available or all at once.
        '''
        NereidCart = Pool().get('nereid.cart')

        cart = NereidCart.open_cart()

        if not cart.sale.shipment_address:
            return redirect(url_for('nereid.checkout.shipping_address'))

        # TODO: Not implemented yet
        return redirect(url_for('nereid.checkout.payment_method'))

    @classmethod
    @route('/checkout/billing-address', methods=['GET', 'POST'])
    @not_empty_cart
    @recent_signin
    @sale_has_non_guest_party
    def billing_address(cls):
        '''
        Choose or Create a billing address
        '''
        NereidCart = Pool().get('nereid.cart')
        Address = Pool().get('party.address')

        cart = NereidCart.open_cart()
        address_form = cls.get_new_address_form(cart.sale.invoice_address)

        if request.method == 'POST':
            if request.form.get('use_shipment_address'):
                if not cart.sale.shipment_address:
                    # Without defining shipment address, the user is
                    # trying to set invoice_address as shipment_address
                    return redirect(
                        url_for('nereid.checkout.shipping_address')
                    )
                cart.sale.invoice_address = cart.sale.shipment_address
                cart.sale.save()
                return redirect(
                    url_for('nereid.checkout.payment_method')
                )

            if not request.is_guest_user and request.form.get('address'):
                # Registered user has chosen an existing address
                address = Address(request.form.get('address', type=int))

                if address.party != cart.sale.party:
                    flash(_('The address chosen is not valid'))
                    return redirect(
                        url_for('nereid.checkout.billing_address')
                    )

            else:
                # Guest user or registered user creating an address. Only
                # difference is that the party of address depends on guest or
                # not
                if not address_form.validate():
                    address = None
                else:
                    if request.is_guest_user and cart.sale.invoice_address \
                        and cart.sale.invoice_address != cart.sale.shipment_address:    # noqa
                        # Save to the same address if the guest user
                        # is just trying to update the address
                        address = cart.sale.invoice_address
                    else:
                        address = Address()

                    address.party = cart.sale.party
                    address.name = address_form.name.data
                    address.street = address_form.street.data
                    address.streetbis = address_form.streetbis.data
                    address.zip = address_form.zip.data
                    address.city = address_form.city.data
                    address.country = address_form.country.data
                    address.subdivision = address_form.subdivision.data
                    address.save()

            if address is not None:
                # Finally save the address to the shipment
                cart.sale.invoice_address = address
                cart.sale.save()

                return redirect(
                    url_for('nereid.checkout.payment_method')
                )

        addresses = []
        if not request.is_guest_user:
            addresses.extend(current_user.party.addresses)

        return render_template(
            'checkout/billing_address.jinja',
            addresses=addresses,
            address_form=address_form,
        )

    @classmethod
    def get_credit_card_form(cls):
        '''
        Return a credit card form.
        '''
        return CreditCardForm()

    @classmethod
    def get_payment_form(cls):
        '''
        Return a payment form
        '''
        NereidCart = Pool().get('nereid.cart')

        cart = NereidCart.open_cart()

        payment_form = PaymentForm()

        # add possible alternate payment_methods
        payment_form.alternate_payment_method.choices = [
            (m.id, m.name) for m in cart.get_alternate_payment_methods()
        ]

        # add profiles of the registered user
        if not request.is_guest_user:
            payment_form.payment_profile.choices = [
                (p.id, p.rec_name) for p in
                current_user.party.get_payment_profiles()
            ]

        if (cart.sale.shipment_address == cart.sale.invoice_address) or (
                not cart.sale.invoice_address):
            payment_form.use_shipment_address.data = "y"

        return payment_form

    @classmethod
    def _process_payment(cls, cart):
        """
        This is separated so that other modules can easily modify the
        behavior of processing payment independent of this module.
        """
        NereidCart = Pool().get('nereid.cart')

        cart = NereidCart.open_cart()
        payment_form = cls.get_payment_form()
        credit_card_form = cls.get_credit_card_form()

        if not request.is_guest_user and payment_form.payment_profile.data:
            # Regd. user with payment_profile
            rv = cart.sale._complete_using_profile(
                payment_form.payment_profile.data
            )
            if isinstance(rv, BaseResponse):
                # Redirects only if payment profile is invalid.
                # Then do not confirm the order, just redirect
                return rv
            return cls.confirm_cart(cart)

        elif payment_form.alternate_payment_method.data:
            # Checkout using alternate payment method
            rv = cart.sale._complete_using_alternate_payment_method(
                payment_form
            )
            if isinstance(rv, BaseResponse):
                # If the alternate payment method introduced a
                # redirect, then save the order and go to that
                cls.confirm_cart(cart)
                return rv
            return cls.confirm_cart(cart)

        elif request.nereid_website.credit_card_gateway and \
                credit_card_form.validate():
            # validate the credit card form and checkout using that
            cart.sale._complete_using_credit_card(credit_card_form)
            return cls.confirm_cart(cart)

    @classmethod
    @route('/checkout/payment', methods=['GET', 'POST'])
    @not_empty_cart
    @recent_signin
    @sale_has_non_guest_party
    @with_company_context
    def payment_method(cls):
        '''
        Select/Create a payment method

        Allows adding new payment profiles for registered users. Guest users
        are allowed to fill in credit card information or chose from one of
        the existing payment gateways.
        '''
        NereidCart = Pool().get('nereid.cart')
        PaymentMethod = Pool().get('nereid.website.payment_method')

        cart = NereidCart.open_cart()
        if not cart.sale.shipment_address:
            return redirect(url_for('nereid.checkout.shipping_address'))

        payment_form = cls.get_payment_form()
        credit_card_form = cls.get_credit_card_form()

        if request.method == 'POST' and payment_form.validate():

            # call the billing address method which will handle any
            # address submission that may be there in this request
            cls.billing_address()

            if not cart.sale.invoice_address:
                # If still there is no billing address. Do not proceed
                # with this
                return redirect(url_for('nereid.checkout.billing_address'))

            rv = cls._process_payment(cart)
            if isinstance(rv, BaseResponse):
                # Return if BaseResponse
                return rv

            flash(_("Error is processing payment."), "warning")

        return render_template(
            'checkout/payment_method.jinja',
            payment_form=payment_form,
            credit_card_form=credit_card_form,
            PaymentMethod=PaymentMethod,
        )

    @classmethod
    def confirm_cart(cls, cart):
        '''
        Confirm the sale, clear the sale from the cart
        '''
        Sale = Pool().get('sale.sale')

        sale = cart.sale
        access_code = None

        if current_user.is_anonymous():
            access_code = unicode(sale.create_guest_access_code())

        Sale.quote([cart.sale])
        Sale.confirm([cart.sale])

        cart.sale = None
        cart.save()

        # Redirect to the order confirmation page
        flash(_(
            "Your order #%(sale)s has been processed",
            sale=sale.reference
        ))

        return redirect(url_for(
            'sale.sale.render', active_id=sale.id, confirmation=True,
            access_code=access_code,
        ))
