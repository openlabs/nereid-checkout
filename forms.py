# -*- coding: utf-8 -*-
"""
    nereid-checkout.form

    Forms used in checkout

    :copyright: (c) 2010-2011 by Openlabs Technologies & Consulting (P) LTD.
    :license: GPLv3, see LICENSE for more details
"""
from wtforms import Form, validators 
from wtforms import TextField, IntegerField, SelectField, PasswordField
from wtforms import RadioField, FormField, BooleanField
from otcltools.general.forms import PreValidatedFormField, IgnoreIfTrueMixin


_REQD = [validators.Required(),]


class DummyPostData(dict):
    """
    Dummy class used instead of post data
    Copied from wtforms test suite

    Copyright (c) 2010 by Thomas Johansson, James Crasta and others.
    """
    def getlist(self, key):
        "Method needed by the validator"
        return self[key]


class CheckoutMethodForm(Form):
    """Default Login Form + method

    Test with no data::
    >>> data = DummyPostData()
    >>> form = CheckoutMethodForm(data)
    >>> form.validate()
    False

    Test with just username and password::
    >>> data = DummyPostData(username="user", password="pass")
    >>> form = CheckoutMethodForm(data)
    >>> form.validate()
    True
    """
    username = TextField('Username', _REQD)
    password = PasswordField('Password', _REQD)


class AddressForm(Form):
    "A Form resembling the res.partner.address"
    name = TextField('Name', _REQD)
    street = TextField('Street', _REQD)
    streetbis = TextField('Street (Bis)')
    zip = TextField('Post Code', _REQD)
    city = TextField('City', _REQD)
    email = TextField('e-mail', _REQD + [validators.Email()])
    phone = TextField('Phone', _REQD)
    # Fields expected to be ajax, will not support a native
    # Submit operation
    country = IntegerField('Country', _REQD)
    subdivision = IntegerField('State/Country', _REQD)


class AddressFormWithPassword(AddressForm):
    """A Form resembling the res.partner.address but with username and password
    Not used at the moment
    """
    username = TextField('Username', _REQD)
    password = PasswordField('Password', [
        validators.Required(),
        validators.EqualTo('confirm', message='Passwords must match')])
    confirm = PasswordField('Repeat Password')


class AddressChoiceForm(Form):
    '''The form allows to choose from an address
    or create a new one
    '''
    address = SelectField('Select Address',
        choices=[('0', 'New Address')],
        coerce=int, validators=_REQD)
    new_address = FormField(AddressForm)


class IgnoreIfTrueFormField(IgnoreIfTrueMixin, PreValidatedFormField):
    """Ignores validation if given condition is True
    """
    pass


class IgnoreIfTrueSelectField(IgnoreIfTrueMixin, SelectField):
    "Ignore the validation if given condition is satisfied in pre validation"
    pass


class OneStepCheckout(Form):
    """Form for a one page checkout

    Test with no data::
    >>> data = DummyPostData()
    >>> form = OneStepCheckout(data)
    >>> form.validate()
    False

    When the shipping_same_as_billing is False check both addresses
    >>> data = DummyPostData()
    >>> form = OneStepCheckout(data)
    >>> form.validate()
    False
    >>> 'new_shipping_address' in form.errors.keys()
    True

    Validate ony billing address when shipping_same_as_billing
    >>> data = DummyPostData(shipping_same_as_billing=True)
    >>> form = OneStepCheckout(data)
    >>> form.validate()
    False
    >>> 'new_shipping_address' in form.errors.keys()
    False

    """
    new_billing_address = FormField(AddressForm)
    shipping_same_as_billing = BooleanField(
        "Use billing address as shipping address")
    new_shipping_address = IgnoreIfTrueFormField(
        'form.shipping_same_as_billing.data', AddressForm)

    #: Since the loading is on AJAX, there is no way to fill
    #: the optons pre-rendering. So take them as integer IDs
    shipment_method = IntegerField('Shipping Method', _REQD)
    payment_method = IntegerField('Payment Method', _REQD)


class OneStepCheckoutRegd(OneStepCheckout):
    """Form to be used by registered users for checkout

    Test with no data::
    >>> data = DummyPostData()
    >>> form = OneStepCheckoutRegd(data)
    >>> form.validate()
    False
    >>> 'billing_address' in form.errors.keys()
    True
    >>> 'shipping_address' in form.errors.keys()
    True

    When the billing address is 0, new_billing_address is to be validated
    >>> data = DummyPostData(billing_address='0', shipping_address='0')
    >>> form = OneStepCheckoutRegd(data)
    >>> form.validate()
    False
    >>> form.billing_address.data
    0
    >>> 'new_billing_address' in form.errors.keys()
    True
    >>> 'new_shipping_address' in form.errors.keys()
    True
    >>> 'billing_address' not in form.errors.keys()
    True
    >>> 'shipping_address' not in form.errors.keys()
    True

    When the billing address is not 0, new_billing_address is not be validated
    >>> data = DummyPostData(billing_address='1')
    >>> form = OneStepCheckoutRegd(data)
    >>> form.billing_address.choices.append((1, 'Existing Address'))
    >>> form.validate()
    False
    >>> 'new_billing_address' in form.errors.keys()
    False

    When the billing address is set and shipping_address is set to copy the
    Billing address:
    >>> data = DummyPostData(billing_address='1', shipping_same_as_billing=True)
    >>> form = OneStepCheckoutRegd(data)
    >>> form.billing_address.choices.append((1, 'Existing Address'))
    >>> form.validate()
    False
    >>> form.errors.keys()
    ['payment_method', 'shipment_method']

    When the billing address is set and shipping_address is also set:
    >>> data = DummyPostData(billing_address='1', shipping_address='1',
    ...     shipment_method='1', payment_method='1')
    >>> form = OneStepCheckoutRegd(data)
    >>> form.billing_address.choices.append((1, 'Existing Address'))
    >>> form.shipping_address.choices.append((1, 'Existing Address'))
    >>> form.validate()
    True
    """
    billing_address = SelectField('Billing Address', coerce=int,
        choices=[(0, 'New Address')])
    new_billing_address = IgnoreIfTrueFormField(
        'form.billing_address.data != 0', AddressForm)

    shipping_address = IgnoreIfTrueSelectField(
        'form.shipping_same_as_billing.data == True',
        'Shipping Address', coerce=int,
        choices=[(0, 'New Address')])
    new_shipping_address = IgnoreIfTrueFormField(
        'form.shipping_same_as_billing.data or form.shipping_address.data != 0',
        AddressForm)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
