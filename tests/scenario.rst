==================================
Nereid Shipping Scenario
==================================

=============
General Setup
=============

Imports::

    >>> from decimal import Decimal
    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from proteus import config, Model, Wizard
    >>> from nereid import Nereid

Create database::

    >>> DBNAME = ':memory:'
    >>> config = config.set_trytond(DBNAME, database_type='sqlite')

Install Nereid Checkout::

    >>> Module = Model.get('ir.module.module')
    >>> modules = Module.find([('name', '=', 'nereid_checkout')])
    >>> len(modules)
    1

    >>> Module.button_install([x.id for x in modules], config.context)
    >>> Wizard('ir.module.module.install_upgrade').execute('start')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> Company = Model.get('company.company')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> company.name = 'OTCL'
    >>> company.currency, = Currency.find([('code', '=', 'EUR')])
    >>> company_config.execute('add')
    >>> company, = Company.find()

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> FiscalYear = Model.get('account.fiscalyear')
    >>> Sequence = Model.get('ir.sequence')
    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> today = datetime.date.today()
    >>> fiscalyear = FiscalYear(name='%s' % today.year)
    >>> fiscalyear.start_date = today + relativedelta(month=1, day=1)
    >>> fiscalyear.end_date = today + relativedelta(month=12, day=31)
    >>> fiscalyear.company = company
    >>> post_move_sequence = Sequence(name='%s' % today.year,
    ...     code='account.move',
    ...     company=company)
    >>> post_move_sequence.save()
    >>> fiscalyear.post_move_sequence = post_move_sequence
    >>> invoice_sequence = SequenceStrict(name='%s' % today.year,
    ...     code='account.invoice',
    ...     company=company)
    >>> invoice_sequence.save()
    >>> fiscalyear.out_invoice_sequence = invoice_sequence
    >>> fiscalyear.in_invoice_sequence = invoice_sequence
    >>> fiscalyear.out_credit_note_sequence = invoice_sequence
    >>> fiscalyear.in_credit_note_sequence = invoice_sequence
    >>> fiscalyear.save()
    >>> FiscalYear.create_period([fiscalyear.id], config.context)
    True

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> AccountJournal = Model.get('account.journal')
    >>> account_template, = AccountTemplate.find([('parent', '=', False)])
    >>> create_chart_account = Wizard('account.account.create_chart_account')
    >>> create_chart_account.execute('account')
    >>> create_chart_account.form.account_template = account_template
    >>> create_chart_account.form.company = company
    >>> create_chart_account.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('kind', '=', 'receivable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> payable, = Account.find([
    ...         ('kind', '=', 'payable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> revenue, = Account.find([
    ...         ('kind', '=', 'revenue'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> expense, = Account.find([
    ...         ('kind', '=', 'expense'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> create_chart_account.form.account_receivable = receivable
    >>> create_chart_account.form.account_payable = payable
    >>> create_chart_account.execute('create_properties')
    >>> stock_journal, = AccountJournal.find([('code', '=', 'STO')])

Create parties::

    >>> Party = Model.get('party.party')
    >>> Address = Model.get('party.address')
    >>> ContactMechanism = Model.get('party.contact_mechanism')
    >>> customer = Party(name='Customer')
    >>> customer.save() 
    >>> email = ContactMechanism(type='email', value='user@example.com', 
    ...     party=customer)
    >>> email.save()
    >>> customer.addresses.append(Address(
    ...     name='Customer Address', email=email, password='password'))
    >>> customer.save()

Create Guest User::

    >>> Party = Model.get('party.party')
    >>> Address = Model.get('party.address')
    >>> ContactMechanism = Model.get('party.contact_mechanism')
    >>> guest = Party(name='Guest')
    >>> guest.save() 
    >>> email = ContactMechanism(type='email', value='guest@example.com', 
    ...     party=guest)
    >>> email.save()
    >>> guest_address = Address(
    ...     name='Guest Address', email=email, 
    ...     password='password', party=guest)
    >>> guest_address.save()
    >>> guest.addresses.append(guest_address)
    >>> guest.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> PaymentTermLine = Model.get('account.invoice.payment_term.line')
    >>> payment_term = PaymentTerm(name='Direct')
    >>> payment_term_line = PaymentTermLine(type='remainder')
    >>> payment_term.lines.append(payment_term_line)
    >>> payment_term.save()

Setup URLs::

    >>> NereidSite = Model.get('nereid.website')
    >>> URLMap = Model.get('nereid.url_map')
    >>> URLRule = Model.get('nereid.url_rule')
    >>> url_map = URLMap(name='Test Map')
    >>> url_map.rules.append(URLRule(rule='/',
    ...     endpoint='nereid.website.home'))
    >>> url_map.rules.append(URLRule(rule='/login',
    ...     endpoint='nereid.website.login', methods='("GET", "POST")'))
    >>> url_map.rules.append(URLRule(rule='/cart', 
    ...     endpoint='nereid.cart.view_cart', methods='("GET", "POST")'))
    >>> url_map.rules.append(URLRule(rule='/cart/add', 
    ...     endpoint='nereid.cart.add_to_cart', methods='("GET", "POST")'))
    >>> url_map.rules.append(URLRule(rule='/checkout', 
    ...     endpoint='nereid.checkout.default.checkout', methods='("GET", "POST")'))
    >>> url_map.save()

Create Templates::

    >>> LangObj = Model.get('ir.lang')
    >>> english, = LangObj.find([('code', '=', 'en_US')])
    >>> Template = Model.get('nereid.template')
    >>> temp_template_id = Template(
    ...     name='temp-replacement.jinja', language=english,
    ...     source=' Test ')
    >>> temp_template_id.save()
    >>> home_template_id = Template(
    ...     name='home.jinja', language=english,
    ...     source=' Home ')
    >>> temp_template_id.save()
    >>> checkout_template = Template(
    ...     name='checkout.jinja', language=english,
    ...     source='{{get_cart_size()|round|int}},{{form.errors}}')
    >>> checkout_template.save()
    >>> login_template = Template(
    ...     name='login.jinja', language=english,
    ...     source=' ')
    >>> login_template.save()
    >>> cart_template = Template(
    ...     name='shopping-cart.jinja', language=english,
    ...     source='Cart:{{ cart.id }},{{get_cart_size()|round|int}},{{cart.sale.total_amount}}')
    >>> cart_template.save()
    >>> product_template = Template(
    ...     name='product.jinja', language=english,
    ...     source=' ')
    >>> product_template.save()
    >>> category_template = Template(
    ...     name='category.jinja', language=english,
    ...     source=' ')
    >>> category_template.save()
    >>> product_list_template = Template(
    ...     name='product-list.jinja', language=english,
    ...     source=' ')
    >>> product_list_template.save()
    >>> category_list_template = Template(
    ...     name='category-list.jinja', language=english,
    ...     source=' ')
    >>> category_list_template.save()

Create category::

    >>> ProductCategory = Model.get('product.category')
    >>> category = ProductCategory(name='Category', 
    ...     nereid_template=category_template)
    >>> category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> product.name = 'product 1'
    >>> product.category = category
    >>> product.default_uom = unit
    >>> product.type = 'stockable'
    >>> product.purchasable = True
    >>> product.salable = True
    >>> product.list_price = Decimal('10')
    >>> product.cost_price = Decimal('5')
    >>> product.account_expense = expense
    >>> product.account_revenue = revenue
    >>> product.account_journal_stock_input = stock_journal
    >>> product.account_journal_stock_output = stock_journal
    >>> product.nereid_template = product_template
    >>> product.save()

Setup Site::

    >>> Country = Model.get('country.country')
    >>> countries = [c.id for c in Country.find([('code', 'in', ('IN', 'US'))])]
    >>> site = NereidSite(name='Test Site', 
    ...     url_map=url_map, company=company.id, countries=countries,
    ...     product_template=product_list_template,
    ...     category_template=category_list_template)
    >>> site.save()

Load the WSGI App::

    >>> from nereid import Nereid
    >>> app = Nereid(
    ...     DATABASE_NAME=DBNAME,
    ...     TRYTON_CONFIG='trytond.conf',
    ...     SITE=site.name, GUEST_USER=guest_address.id)
    >>> app.debug=True
    >>> app.site
    u'Test Site'

Build and Checkout::

    >>> with app.test_client() as c:
    ...     cart_response1 = c.get('/cart')
    ...     cart_response1
    ...     # Add the product to Cart
    ...     c.post('/cart/add', data={'product': product.id, 'quantity': 5})
    ...     cart_response2 = c.get('/cart')
    ...     cart_response2
    ...     cart_response1 == cart_response2
    ...     # Check if a sale order is created
    ...     Sale = Model.get('sale.sale')
    ...     sales = Sale.find([])
    ...     len(sales)
    ...     sale = sales[0]
    ...     sale.state
    ...     len(sale.lines)
    ...     line = sale.lines[0]
    ...     line.product.id
    ...     line.quantity
    ...     # Begin the checkout
    ...     c.get('/checkout')
    ...     # Post with empty form for checkout and assert it fails
    ...     response = c.post('/checkout', data={})
    ...     response
    ...     'payment_method' in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' in response.data
    ...     # Post with the city for both fields and assert they are taken
    ...     response = c.post('/checkout', data={
    ...         'new_billing_address-city': 'Delhi',
    ...         'new_shipping_address-city': 'New Delhi',
    ...         })
    ...     response
    ...     'payment_method' in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' in response.data
    ...     'city' not in response.data
    ...     # Post with the billing address partly filled up and the
    ...     # shipping_same_as_billing as True
    ...     response = c.post('/checkout', data={
    ...         'new_billing_address-city': 'Delhi',
    ...         'shipping_same_as_billing': True,
    ...         'payment_method': 1,
    ...         })
    ...     response
    ...     'payment_method' not in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' not in response.data
    ...     # Post with the billing address, completed and 
    ...     # shipping_same_as_billing and ensure that the guest partner
    ...     # now has two addresses and the invoice order_id, billing_id
    ...     # are all the same.
    ...     country = Country.find([])[0]
    ...     subdivision = country.subdivisions[0]
    ...     response = c.post('/checkout', data={
    ...         'new_billing_address-name'          : 'Name',
    ...         'new_billing_address-street'        : 'Street',
    ...         'new_billing_address-streetbis'     : 'Street2',
    ...         'new_billing_address-zip'           : 'ZIP',
    ...         'new_billing_address-city'          : 'City',
    ...         'new_billing_address-email'         : 'email@example.com',
    ...         'new_billing_address-phone'         : '1234567',
    ...         'new_billing_address-country'       : country.id,
    ...         'new_billing_address-subdivision'   : subdivision.id,
    ...         'shipping_same_as_billing'          : True,
    ...         'shipment_method'                   : 1,
    ...         'payment_method'                    : 1,
    ...         })
    ...     response
    <Response streamed [200 OK]>
    <Response streamed [302 FOUND]>
    <Response streamed [200 OK]>
    False
    1
    u'draft'
    1
    1
    5.0
    <Response streamed [200 OK]>
    <Response streamed [200 OK]>
    True
    True
    True
    True
    <Response streamed [200 OK]>
    True
    True
    True
    True
    True
    <Response streamed [200 OK]>
    True
    True
    True
    True
    <Response streamed [302 FOUND]>
    
Build and Checkout for a logged in user::

    >>> with app.test_client() as c:
    ...     c.post('/login', 
    ...         data=dict(email='user@example.com', password='password'))
    ...     cart_response1 = c.get('/cart')
    ...     cart_response1
    ...     # Add the product to Cart
    ...     c.post('/cart/add', data={'product': product.id, 'quantity': 5})
    ...     cart_response2 = c.get('/cart')
    ...     cart_response2
    ...     cart_response1 == cart_response2
    ...     # Check if a sale order is created
    ...     Sale = Model.get('sale.sale')
    ...     sales = Sale.find([])
    ...     len(sales)
    ...     sale = sales[0]
    ...     sale.state
    ...     len(sale.lines)
    ...     line = sale.lines[0]
    ...     line.product.id
    ...     line.quantity
    ...     # Begin the checkout
    ...     c.get('/checkout')
    ...     # Post with empty form for checkout and assert it fails
    ...     response = c.post('/checkout', data={})
    ...     response
    ...     'payment_method' in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' in response.data
    ...     # Post with the city for both fields and assert they are taken
    ...     response = c.post('/checkout', data={
    ...         'new_billing_address-city': 'Delhi',
    ...         'new_shipping_address-city': 'New Delhi',
    ...         })
    ...     response
    ...     'payment_method' in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' in response.data
    ...     'city' not in response.data
    ...     # Post with the billing address partly filled up and the
    ...     # shipping_same_as_billing as True
    ...     response = c.post('/checkout', data={
    ...         'new_billing_address-city': 'Delhi',
    ...         'shipping_same_as_billing': True,
    ...         'payment_method': 1,
    ...         })
    ...     response
    ...     'payment_method' not in response.data
    ...     'new_billing_address' in response.data
    ...     'shipment_method' in response.data
    ...     'new_shipping_address' not in response.data
    ...     # Post with the billing address, completed and 
    ...     # shipping_same_as_billing and ensure that the guest partner
    ...     # now has two addresses and the invoice order_id, billing_id
    ...     # are all the same.
    ...     country = Country.find([])[0]
    ...     subdivision = country.subdivisions[0]
    ...     response = c.post('/checkout', data={
    ...         'billing_address'                   : '0',
    ...         'new_billing_address-name'          : 'Name',
    ...         'new_billing_address-street'        : 'Street',
    ...         'new_billing_address-streetbis'     : 'Street2',
    ...         'new_billing_address-zip'           : 'ZIP',
    ...         'new_billing_address-city'          : 'City',
    ...         'new_billing_address-email'         : 'email@example.com',
    ...         'new_billing_address-phone'         : '1234567',
    ...         'new_billing_address-country'       : country.id,
    ...         'new_billing_address-subdivision'   : subdivision.id,
    ...         'shipping_same_as_billing'          : True,
    ...         'shipment_method'                   : 1,
    ...         'payment_method'                    : 1,
    ...         })
    ...     response
    <Response streamed [200 OK]>
    <Response streamed [302 FOUND]>
    <Response streamed [200 OK]>
    False
    2
    u'draft'
    1
    1
    5.0
    <Response streamed [200 OK]>
    <Response streamed [200 OK]>
    True
    False
    True
    False
    <Response streamed [200 OK]>
    True
    False
    True
    False
    True
    <Response streamed [200 OK]>
    True
    False
    True
    True
    <Response streamed [302 FOUND]>
