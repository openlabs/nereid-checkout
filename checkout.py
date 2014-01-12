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
    login_required, current_app
from nereid.signals import login, logout, failed_login
from nereid.globals import session
from wtforms import Form, TextField, RadioField, validators, PasswordField, \
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

    If you want to change the time duration, subclass and implement the
    :meth:`Checkout.is_recent_signin` method.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        Checkout = Pool().get('nereid.checkout')
        if not request.is_guest_user:
            sign_in_at = session.get('checkout-sign-in-at', datetime.min)
            if not Checkout.is_recent_signin(sign_in_at):
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

    def validate_password(self, field):
        if self.checkout_mode.data == 'account' and not field.data:
            raise ValidationError(_('Password is required.'))


class Checkout(ModelView):
    'A checkout model'
    __name__ = 'nereid.checkout'

    @classmethod
    def is_recent_signin(cls, sign_in_time):
        """
        Returns True if the signin time given is considered recent enough.

        :param sign_in_time: UTC Datetime instance
        """
        return (datetime.utcnow() - sign_in_time).total_seconds() < 60 * 60

    @staticmethod
    @logout.connect
    @failed_login.connect
    def clear_signin_time(*args, **kwargs):
        """
        Clear the time so that the next checkout does not loop between signin
        and shipment
        """
        session.pop('checkout-sign-in-at', None)

    @classmethod
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
                request.form,
                email=request.nereid_user.email,
                checkout_mode='account',
            )
        else:
            # Guest user
            form = CheckoutSignInForm(
                request.form,
                email=session.get('email'),
                checkout_mode='guest',
            )

        if request.method == 'POST' and form.validate():
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
                        'email': form.email.data,
                        'addresses': [],
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
                    party.email = form.email.data
                    party.save()

                return redirect(
                    url_for('nereid.checkout.shipping_address')
                )
            else:
                print "Authenticating user"
                # The user wants to use existing email to login
                result = NereidUser.authenticate(
                    form.email.data, form.password.data
                )
                print "result", result
                if result:
                    session['user'] = result.id
                    session['email'] = form.email.data
                    session['checkout-sign-in-at'] = datetime.utcnow()
                    login.send()
                    return redirect(
                        url_for('nereid.checkout.shipping_address')
                    )
                else:
                    failed_login.send()

        if cls.is_recent_signin(
                session.get('checkout-sign-in-at', datetime.min)):
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

                    print "saving to address", address, address_form.data

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
            addresses.extend(request.nereid_user.party.addresses)

        return render_template(
            'checkout/shipping_address.jinja',
            addresses=addresses,
            address_form=address_form,
        )

    @classmethod
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
            addresses.extend(request.nereid_user.party.addresses)

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
        return CreditCardForm(request.form)

    @classmethod
    def get_payment_form(cls):
        '''
        Return a payment form
        '''
        NereidCart = Pool().get('nereid.cart')

        cart = NereidCart.open_cart()

        payment_form = PaymentForm(request.form)

        # add possible alternate payment_methods
        payment_form.alternate_payment_method.choices = [
            (m.id, m.name) for m in cart.get_alternate_payment_methods()
        ]

        # add profiles of the registered user
        if not request.is_guest_user:
            payment_form.payment_profile.choices = [
                (p.id, p.rec_name) for p in
                request.nereid_user.party.get_payment_profiles()
            ]

        if (cart.sale.shipment_address == cart.sale.invoice_address) or (
                not cart.sale.invoice_address):
            print "use shipping address"
            payment_form.use_shipment_address.data = "y"

        return payment_form

    @classmethod
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

            if not request.is_guest_user and payment_form.payment_profile.data:
                # Regd. user with payment_profile
                rv = cls.complete_using_profile(
                    payment_form.payment_profile.data
                )
                if isinstance(rv, BaseResponse):
                    # Redirects only if payment profile is invalid.
                    # Then do not confirm the order, just redirect
                    return rv
                return cls.confirm_cart(cart)

            elif payment_form.alternate_payment_method.data:
                # Checkout using alternate payment method
                rv = cls.complete_using_alternate_payment_method(
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
                cls.complete_using_credit_card(credit_card_form)
                return cls.confirm_cart(cart)

            flash(_("Error is processing payment."), "warning")

        return render_template(
            'checkout/payment_method.jinja',
            payment_form=payment_form,
            credit_card_form=credit_card_form,
            PaymentMethod=PaymentMethod,
        )

    @classmethod
    def complete_using_credit_card(cls, credit_card_form):
        '''
        Complete using the given card.

        If the user is registered and the save card option is given, then
        first save the card and delegate to :meth:`complete_using_profile`
        with the profile thus obtained.

        Otherwise a payment transaction is created with the given card data.
        '''
        NereidCart = Pool().get('nereid.cart')
        AddPaymentProfileWizard = Pool().get(
            'party.party.payment_profile.add', type='wizard'
        )
        TransactionUseCardWizard = Pool().get(
            'payment_gateway.transaction.use_card', type='wizard'
        )
        PaymentTransaction = Pool().get('payment_gateway.transaction')

        sale = NereidCart.open_cart().sale
        gateway = request.nereid_website.credit_card_gateway

        if not request.is_guest_user and \
                credit_card_form.add_card_to_profiles.data and \
                request.nereid_website.save_payment_profile:
            profile_wiz = AddPaymentProfileWizard(
                AddPaymentProfileWizard.create()[0]     # Wizard session
            )

            profile_wiz.card_info.party = sale.party
            profile_wiz.card_info.address = sale.invoice_address
            profile_wiz.card_info.provider = gateway.provider
            profile_wiz.card_info.gateway = gateway
            profile_wiz.card_info.owner = credit_card_form.owner.data
            profile_wiz.card_info.number = credit_card_form.number.data
            profile_wiz.card_info.expiry_month = \
                credit_card_form.expiry_month.data
            profile_wiz.card_info.expiry_year = \
                credit_card_form.expiry_year.data
            profile_wiz.card_info.csc = credit_card_form.cvv.data

            with Transaction().set_context(return_profile=True):
                profile = profile_wiz.transition_add()
                return cls.complete_using_profile(profile.id)

        # Manual card based operation
        payment_transaction = PaymentTransaction(
            party=sale.party,
            address=sale.invoice_address,
            amount=sale.amount_to_receive,
            currency=sale.currency,
            gateway=gateway,
            sale=sale,
        )
        payment_transaction.save()

        use_card_wiz = TransactionUseCardWizard(
            TransactionUseCardWizard.create()[0]        # Wizard session
        )
        use_card_wiz.card_info.owner = credit_card_form.owner.data
        use_card_wiz.card_info.number = credit_card_form.number.data
        use_card_wiz.card_info.expiry_month = \
            credit_card_form.expiry_month.data
        use_card_wiz.card_info.expiry_year = \
            credit_card_form.expiry_year.data
        use_card_wiz.card_info.csc = credit_card_form.cvv.data

        with Transaction().set_context(active_id=payment_transaction.id):
            use_card_wiz.transition_capture()

    @classmethod
    def complete_using_alternate_payment_method(cls, payment_form):
        '''
        :param payment_form: The validated payment_form to extract additional
                             info
        '''
        NereidCart = Pool().get('nereid.cart')
        PaymentTransaction = Pool().get('payment_gateway.transaction')
        PaymentMethod = Pool().get('nereid.website.payment_method')

        sale = NereidCart.open_cart().sale
        payment_method = PaymentMethod(
            payment_form.alternate_payment_method.data
        )

        payment_transaction = PaymentTransaction(
            party=sale.party,
            address=sale.invoice_address,
            amount=sale.amount_to_receive,
            currency=sale.currency,
            gateway=payment_method.gateway,
            sale=sale,
        )
        payment_transaction.save()

        return payment_method.process(payment_transaction)

    @classmethod
    @login_required
    def complete_using_profile(cls, payment_profile_id):
        '''
        Complete the Checkout using a payment_profile. Only available to the
        registered users of the website.


        * payment_profile: Process the payment profile for the transaction
        '''
        NereidCart = Pool().get('nereid.cart')
        PaymentProfile = Pool().get('party.payment_profile')
        PaymentTransaction = Pool().get('payment_gateway.transaction')

        payment_profile = PaymentProfile(payment_profile_id)

        if payment_profile.party != request.nereid_user.party:
            # verify that the payment profile belongs to the registered
            # user.
            flash(_('The payment profile chosen is invalid'))
            return redirect(
                url_for('nereid.checkout.payment_method')
            )

        sale = NereidCart.open_cart().sale
        payment_transaction = PaymentTransaction(
            party=sale.party,
            address=sale.invoice_address,
            payment_profile=payment_profile,
            amount=sale.amount_to_receive,
            currency=sale.currency,
            gateway=payment_profile.gateway,
            sale=sale,
        )
        payment_transaction.save()

        PaymentTransaction.capture([payment_transaction])

    @classmethod
    def confirm_cart(cls, cart):
        '''
        Confirm the sale, clear the sale from the cart
        '''
        Sale = Pool().get('sale.sale')

        Sale.quote([cart.sale])
        Sale.confirm([cart.sale])

        sale = cart.sale

        cart.sale = None
        cart.save()

        # Redirect to the order confirmation page
        flash(_(
            "Your order #%(sale)s has been processed",
            sale=sale.reference
        ))
        if request.is_guest_user:
            access_code = sale.create_guest_access_code()
            return redirect(url_for(
                'sale.sale.render',
                active_id=sale.id,
                confirmation=True,
                access_code=unicode(access_code),
            ))
        else:
            return redirect(
                url_for(
                    'sale.sale.render', active_id=sale.id,
                    confirmation=True
                )
            )
