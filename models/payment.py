# -*- coding: utf-8 -*-

import json
import datetime
import time
import base64
import re
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError
import logging

from werkzeug import urls

from odoo import api, fields, models, tools, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_mpesa.controllers.main import MpesaController

_logger = logging.getLogger(__name__)


class PaymentAcquirer(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('mpesa', 'Mpesa')])
    mpesa_secrete_key = fields.Char("Secret key", required_if_provider="mpesa")
    mpesa_customer_key = fields.Char("Customer key", 
                                    required_if_provider="mpesa")
    mpesa_short_code = fields.Char("Shortcode", required_if_provider="mpesa")
    mpesa_pass_key = fields.Char("Pass key", required_if_provider="mpesa")
    # mpesa_description = fields.Char(
    #     "Description", required_if_provider="mpesa")
    # mpesa_reference_number = fields.Char(
    #     "Reference", required_if_provider="mpesa")

    # FIXME: DRY!!!!!!
    @api.model
    def create(self, vals):
        result = super(PaymentAcquirer, self).create(vals)
        if self._mpesa_check_currency():
            return result
        else:
            raise ValidationError(_("""
                                    Please create and activate KES (Kenyan Currency).
                                    MPesa Acquirer uses Kenyan Currency Only. And
                                    will convert all amounts to Kenyan Currency"""))
    
    # FIXME: DRY!!!!!!
    def write(self, vals):
        result = super(PaymentAcquirer, self).write(vals)
        if self._mpesa_check_currency():
            return result
        else:
            raise ValidationError(_("""
                                    Please create and activate KES (Kenyan Currency).
                                    MPesa Acquirer uses Kenyan Currency Only. And
                                    will convert all amounts to Kenyan Currency"""))

    def _mpesa_check_currency(self):
        """
        """
        KES = self.env['res.currency'].search([('name', '=', 'KES')])
        if KES.active and KES.rate:
            return True
        return False

    @api.model
    def _mpesa_format_phone_number(self, phone):
        """
        M-Pesa requires the amount to be more than or equal to 10 KES.
        """
        phone_regex = re.compile(r'(2547|\+2547|07|7)(\d{8})')
        match_object = phone_regex.search(phone)
        if match_object:
            return '2547' + match_object.group(2)
        return False

    def _get_mpesa_urls(self):
        """ M-Pesa URLs """
        # TODO: Change the keys to match command id values
        # TODO: Add all the urls you need
        environment = self._get_mpesa_environment()
        if environment == 'prod':
            return {
                'mpesa_form_url': '/payment/mpesa/confirm/',
                'access_token': 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials',

                'register': 'https://sandbox.safaricom.co.ke/mpesa/c2b/v1/registerurl', 

                'stk_push': 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest', # CustomerPayBillOnline
                'simulate': 'https://sandbox.safaricom.co.ke/mpesa/c2b/v1/simulate', # CustomerPayBillOnline
                'refund': 'https://sandbox.safaricom.co.ke/mpesa/reversal/v1/request', # TransactionReversal
                'status': 'https://sandbox.safaricom.co.ke/mpesa/transactionstatus/v1/query', # TransactionStatusQuery
                'stk_push_status': 'https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query' 
            }
        return {
            'mpesa_form_url': '/payment/mpesa/confirm/',
            'access_token': 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials',
            'stk_push': 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        }

    # TODO: _mpesa_compute_fees

    # FIXME: This method is not necessary
    def mpesa_form_generate_values(self, values):
        mpesa_tx_values = dict(values)
        mpesa_tx_values.update({
        })
        return mpesa_tx_values

    def mpesa_get_form_action_url(self):
        self.ensure_one()
        return self._get_mpesa_urls()['mpesa_form_url']

    def _get_mpesa_environment(self):
        return 'prod' if self.state == 'enabled' else 'test'

    def mpesa_request(self, values={}, auth=False):
        self.ensure_one()
        # url = urls.url_join(self._get_mpesa_urls(), url)
        
        if auth:
            url = self._get_mpesa_urls()['access_token']
            response = requests.get(url, auth=HTTPBasicAuth(
                self.mpesa_customer_key, self.mpesa_secrete_key))
            json_data = json.loads(response.text)
            # TODO: Handle not successful scenarios as well
            return json_data['access_token']

        # TODO: Get the correct url!!!!
        url = self._get_mpesa_urls()[values['url']]
        headers = {
            'Authorization': 'Bearer %s' % self._mpesa_get_access_token()
            }
        data = self._mpesa_get_request_data(values)
        _logger.info(data)
        data.pop('url')
        resp = requests.post(url, json=data, headers=headers)
        # TODO: Happy path first
        # FIXME: Check that this works 
        if not resp.ok and not (400 <= resp.status_code < 500 and resp.json().get('error', {}).get('code', '')):
            try:
                resp.raise_for_status()
            except HTTPError:
                _logger.error(resp.text)
                mpesa_error = resp.json().get('error', {}).get('message', '')
                error_msg = " " + (_("MPesa gave us the following info about the problem: '%s'") % mpesa_error)
                raise ValidationError(error_msg)
        return resp.json()

    # TODO: Mpesa response validation methods

    def _mpesa_get_access_token(self):
        return self.mpesa_request(auth=True)

    # TODO: Move this to tx, easier to call crap
    # TODO: Add value options based on command_id or something
    def _mpesa_get_request_data(self, values):
        self.ensure_one()
        base_url = self.get_base_url()

        time_stamp = str(time.strftime('%Y%m%d%H%M%S'))
        passkey = self.mpesa_short_code + self.mpesa_pass_key + time_stamp
        password = str(base64.b64encode(passkey.encode('utf-8')), 'utf-8')
        phone = self._mpesa_format_phone_number(values['PartyA'])

        if values['url'] == 'stk_push':
            # TODO: Remove url from the values
            values.update({
                "BusinessShortCode": self.mpesa_short_code,
                "Password": password,
                "Timestamp": time_stamp,
                "PartyB": self.mpesa_short_code,
                "CallBackURL": 'https://demo13.kylix.online/payment/mpesa/callback/',
            })
        elif values['url'] == 'register':
            values.update({
                "ShortCode": self.mpesa_short_code,
                "ResponseType": "Confirmed",
                "ConfirmationURL": urls.url_join(base_url, MpesaController._confirmation_url),
                "ValidationURL": urls.url_join(base_url, MpesaController._validation_url)
            })
        elif values['url'] == 'simulate':
            values.update({}
                # TODO: Add values here
            )
        elif values['url'] == 'refund':
            values.update({
                "Initiator":" ",
                "SecurityCredential":" ",
                "CommandID":"TransactionReversal",
                "ResultURL":"https://ip_address:port/result_url",
                "QueueTimeOutURL":"https://ip_address:port/timeout_url",
            })
        elif values['url'] == 'status':
            values.update({
                "Initiator":" ",
                "SecurityCredential":" ",
                "CommandID":"TransactionStatusQuery",
                "ResultURL":"https://ip_address:port/result_url",
                "QueueTimeOutURL":"https://ip_address:port/timeout_url",
            })
        elif values['url'] == 'stk_push_status':
            values.update({
                "BusinessShortCode": self.mpesa_short_code,
                "Password": password,
                # FIXME: Is this the current time_stamp or that of tx 
                "Timestamp": time_stamp,
            })
        return values

    # LipaNaMpesa Method
    # TODO: Add a button on interface for this, must be done as you save
    # make button invisible if state is disabled 
    def action_mpesa_register_urls(self):
        values = {
            'url': 'register'
        }
        if self.state != 'disabled':
            response = self.mpesa_request(values)
        # TODO: Figure out what to do with the response
        # return self._mpesa_s2s_validate(response)
        pass
    
    # LipaNaMpesa Method
    # TODO: Add a button on the interface for this
    # TODO: Add tests to run many txs
    # TODO: Add a function that accepts values optionally
    # TODO: Add another button to run multiple txs
    def action_mpesa_simulate_tx(self):
        values = {
            'url': 'simulate'
        }
        if self.state is not 'disabled':
            response = self.mpesa_request(values)
        # TODO: Figure out what to do with the response
        pass

    
class TxMpesa(models.Model):
    _inherit = 'payment.transaction'

# RETURN VALUES From MPESA AND WHAT THEY MEAN Result_Code
    _mpesa_result_codes = {
        0: "Success",
        1: "Insufficient Funds",
        2: "Less Than Minimum Transaction Value",
        3: "More Than Maximum Transaction Value",
        4: "Would Exceed Daily Transfer Limit",
        5: "Would Exceed Minimum Balance",
        6: "Unresolved Primary Party",
        7: "Unresolved Receiver Party",
        8: "Would Exceed Maxiumum Balance",
        11: "Debit Account Invalid",
        12: "Credit Account Invalid",
        13: "Unresolved Debit Account",
        14: "Unresolved Credit Account",
        15: "Duplicate Detected",
        17: "Internal Failure",
        20: "Unresolved Initiator",
        26: "Traffic blocking condition in place",
    }
    _mpesa_client_responses = {
        0: 'Success', # (for C2B)
        00000000: 'Success', # (For APIs that are not C2B)
        1: 'Reject', # 1 or any other number	Rejecting the transaction
    }
    _mpesa_identifier_types = {
        1: 'MSISDN',
        2: 'Till Number',
        4: 'Shortcode'
    }
    
    # TODO: This is not useful
    mpesa_command_id = fields.Selection([
        ('CustomerPayBillOnline', 'LipaNaMpesa'), # c2b
        # ('TransactionReversal', 'Reverse C2B Tx'), 
        # TODO: Add a distinction between till and bill field in contacts
        ('BusinessBuyGoods', 'Till B2B'), # b2b
        ('BusinessPayBill', 'Paybill B2B'), # b2b
        # ('CheckIdentity', 'Check Identity'),
        # ('TransactionStatusQuery', 'Tx Status'),
        # FIXME: This can be generalized as a transfer
        # ('BusinessTransferFromMMFToUtility', 'Paybill MMF Transfer'),
        # ('BusinessToBusinessTransfer', 'B2B MMF Transfer'),
        # ('DisburseFundsToBusiness', 'Utility to MMF Transfer'),
        # ('AccountBalance', 'Check Balance'),
        ('PromotionPayment', 'Promotion Payment'), # b2c
        ('BusinessPayment', 'B2C'),
        ('SalaryPayment', 'Salary Payment'), # b2c
        # ('CustomerPaybillOnline', 'Stk Push'),
    ], string='MPesa Command ID', 
    default='CustomerPayBillOnline'
    )
    # TODO: Consider adding a field to differentiate between the various types of txns
    # ie B2B, B2C, C2B, LipaNaMpesa
    mpesa_amount = fields.Monetary(string='MPesa Amount',
    #  currency_field='mpesa_currency_id', 
     store=True, 
     readonly=True, 
     compute='_compute_mpesa_amount_currency'
     )
    # mpesa_currency_id = fields.Many2one('res.currency', 'MPesa Currency', 
    # required=True, readonly=True, store=True, compute='_compute_mpesa_amount_currency')
    mpesa_tx_phone = fields.Char(string='MPesa Billing Phone')
    mpesa_pos_tx = fields.Boolean(string='Is POS TX?', default=False, readonly=True)
    # HACK: Just make this a char
    pos_order_id = fields.Many2one('pos.order', string='Pos Order')
    checkout_request_id = fields.Char(string='Checkout Request ID', readonly=True, default=None)
    merchant_request_id = fields.Char(string='Merchant Request ID', readonly=True, default=None)
    # TODO: Add boolean for reversed C2B txn

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------
    
    @api.model
    def mpesa_create(self, values):
        # TODO: Add command_id selection, not here though
        # if values['partner_id']:
        #     values['type'] = 'server2server'
        #     values['mpesa_tx_phone'] = values['partner_phone']
        # else:
        #     values['type'] = 'form'
        return values

    @api.depends('amount', 'currency_id')
    def _compute_mpesa_amount_currency(self):
        # self.ensure_one()
        # TODO: Add a contingency, in case it does not exist
        # TODO: Add a way to ensure the currency is active --pre init hook
        # Also, what are the implications of hard coding the currency name 'KES'?
        # KES = self.env['res.currency'].search([('name', '=', 'KES')])
        for tx in self:
            # tx.mpesa_currency_id = KES
            # tx.mpesa_amount = tx.currency_id.compute(tx.amount, KES)
            tx.mpesa_amount = tx.amount

    def _mpesa_get_request_data(self, **options):
        self.ensure_one()
        # TODO: Add structure options based on command_id 
        if options['pay']:
            if self.mpesa_pos_tx:
               return {
                # TODO: Add url options here
                "url": 'stk_push',
                "TransactionType": 'CustomerPayBillOnline',
                "Amount": self.mpesa_amount,
                "PartyA": self.mpesa_tx_phone,
                "PhoneNumber": self.mpesa_tx_phone,
                # FIXME: How to capture the pos order number
                # FIXME: If you decide to go char way
                "AccountReference": self.pos_order_id.display_name,
                "TransactionDesc": self.reference
            } 
            return {
                # TODO: Add url options here
                "url": 'stk_push',
                "TransactionType": self.mpesa_command_id,
                "Amount": 10,
                "PartyA": self.mpesa_tx_phone,
                "PhoneNumber": self.mpesa_tx_phone,
                "AccountReference": self.partner_name,
                "TransactionDesc": self.reference
            }
        elif options['refund']:
            return {
                "url": 'refund',
                "TransactionID": self.acquirer_reference,
                "RecieverIdentifierType":"1",
                "Amount": self.mpesa_amount,
                "ReceiverParty": self.mpesa_tx_phone,
                "Remarks":"Refund for %s" % self.reference,
                "Occasion":" "
            }
        elif options['status']:
            return {
                "url": 'status',
                "TransactionID": self.acquirer_reference,
                "PartyA":" ",
                "IdentifierType":"1",
                "Remarks":" ",
                "Occasion":" "
            }
        elif options['stk_status']:
            return {
                "url": 'stk_push_status',
                "CheckoutRequestID": self.acquirer_reference
            }

    def mpesa_s2s_do_transaction(self, **data):
        self.ensure_one()
        values = self._mpesa_get_request_data(pay=True)
        response = self.acquirer_id.mpesa_request(values)
        # TODO: Change this validate to check for different things
        return self._mpesa_s2s_validate(response)

    def mpesa_s2s_void_transaction(self):
        # TODO: IDK but 1 or any other number	Rejecting the transaction
        self.ensure_one()
        pass

    def mpesa_s2s_do_refund(self, **kwargs):
        self.ensure_one()
        # Must find a way to distinguish between c2b etc
        # TODO: Add logic that determines MSISDN and thus phone/shortcode
        values = self._mpesa_get_request_data(refund=True)
        response = self.acquirer_id.mpesa_request(values)
        return self._mpesa_s2s_validate(response)

    def _mpesa_s2s_validate(self, data):
        # TODO: set txns with already returned stuff from acquirer
        _logger.info(data)
        # status = data['Body']['stkCallback'].get('ResultCode')
        status = data.get('ResponseCode')
        # TODO: Get errorCode and errorMessage from response
        # error = data.get('errorCode')
        _logger.info(status)
        error_message = data.get('errorMessage')
        if status == '0':
            _logger.info('status 0')
            if data.get('MpesaReceiptNumber'):
                _logger.info('done ' + data.get('MpesaReceiptNumber'))
                self.write({'acquirer_reference': data.get('MpesaReceiptNumber')})
                self._set_transaction_done()
                return True
            else:
                _logger.info('pending')
                self.write({'state_message': data.get('ResponseDescription'),
                            'checkout_request_id': data.get('CheckoutRequestID'),
                            'merchant_request_id': data.get('MerchantRequestID'),
                })
                self._set_transaction_pending()
                return True
        # TODO: Look at all the ResultCodes for status pending possibilities
        else:
            if status == 1032: # <str> or <int>
                errorMessage = _('M-Pesa: The customer rejected the transaction')
            else:
                errorMessage = _(error_message)
            _logger.info(errorMessage)
            _logger.info('cancel')
            self.write({'state_message': errorMessage})
            self._set_transaction_cancel()
            return False

    def _mpesa_s2s_get_tx_status(self):
        self.ensure_one()
        if self.mpesa_command_id == 'CustomerPayBillOnline':
            values = self._mpesa_get_request_data(stk_status=True)
        else:
            values = self._mpesa_get_request_data(status=True)
        response = self.acquirer_id.mpesa_request(values)
        return self._mpesa_s2s_validate(response)
        # TODO: Add logic for tx query

    @api.model
    def _mpesa_form_get_tx_from_data(self, data):
        checkout_request_id = data.get('CheckoutRequestID')
        if not checkout_request_id:
            error_msg = _('Mpesa: received data with missing reference (%s)') % (checkout_request_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use pspReference ?
        tx = self.env['payment.transaction'].search([('checkout_request_id', '=', checkout_request_id)])
        if not tx or len(tx) > 1:
            error_msg = _('Mpesa: received data for CheckoutRequestID %s') % (checkout_request_id)
            if not tx:
                error_msg += _('; no order found')
            else:
                error_msg += _('; multiple order found')
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        return tx

    def _mpesa_form_get_invalid_parameters(self, data):
        invalid_parameters = []

        # reference at acquirer: pspReference
        if self.acquirer_reference and data.get('pspReference') != self.acquirer_reference:
            invalid_parameters.append(('pspReference', data.get('pspReference'), self.acquirer_reference))
        # CheckoutRequestID
        if data.get('CheckoutRequestID') != self.checkout_request_id:
            invalid_parameters.append(('CheckoutRequestID', data.get('CheckoutRequestID'), self.checkout_request_id))
        # MerchantRequestID
        if data.get('MerchantRequestID') != self.merchant_request_id:
            invalid_parameters.append(('MerchantRequestID', data.get('MerchantRequestID'), self.merchant_request_id))
        
        return invalid_parameters

    def _mpesa_form_validate(self, data):
        
        self._set_transaction_done()
        # status = data.get('authResult', 'PENDING')
        # if status == 'AUTHORISED':
        #     self.write({'acquirer_reference': data.get('pspReference')})
        #     self._set_transaction_done()
        #     return True
        # elif status == 'PENDING':
        #     self.write({'acquirer_reference': data.get('pspReference')})
        #     self._set_transaction_pending()
        #     return True
        # else:
        #     error = _('Adyen: feedback error')
        #     _logger.info(error)
        #     self.write({'state_message': error})
        #     self._set_transaction_cancel()
        #     return False





# ********************************************************************************************************************************************************* #
# TODO: Add class for account.payment
# TODO: Add way to make a payment method for inbound/out

# TODO: Add b2c payment Salary, Promotion, 
# POST https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest
#  request = {
#     "InitiatorName": " ",
#     "SecurityCredential":" ",
#     "CommandID": " ",
#     "Amount": " ",
#     "PartyA": " ",
#     "PartyB": " ",
#     "Remarks": " ",
#     "QueueTimeOutURL": "http://your_timeout_url",
#     "ResultURL": "http://your_result_url",
#     "Occasion": " "
#   }
# InitiatorName	This is the credential/username used to authenticate the transaction request.
# SecurityCredential	Base64 encoded string of the B2C short code and password, which is encrypted using M-Pesa public key and validates the transaction on M-Pesa Core system.
# CommandID	Unique command for each transaction type e.g. SalaryPayment, BusinessPayment, PromotionPayment
# Amount	The amount being transacted
# PartyA	Organization’s shortcode initiating the transaction.
# PartyB	Phone number receiving the transaction
# Remarks	Comments that are sent along with the transaction.
# QueueTimeOutURL	The timeout end-point that receives a timeout response.
# ResultURL	The end-point that receives the response of the transaction
# Occasion	Optional

# TODO: Add b2b payment Vendor, 
# POST https://sandbox.safaricom.co.ke/mpesa/b2b/v1/paymentrequest
# request = {
#     "Initiator": " ",
#     "SecurityCredential": " ",
#     "CommandID": " ",
#     "SenderIdentifierType": " ",
#     "RecieverIdentifierType": " ",
#     "Amount": " ",
#     "PartyA": " ",
#     "PartyB": " ",
#     "AccountReference": " ",
#     "Remarks": " ",
#     "QueueTimeOutURL": "http://your_timeout_url",
#     "ResultURL": "http://your_result_url"
#   }
# Initiator	This is the credential/username used to authenticate the transaction request.
# SecurityCredential	Base64 encoded string of the B2B short code and password, which is encrypted using M-Pesa public key and validates the transaction on M-Pesa Core system.
# CommandID	Unique command for each transaction type, possible values are: BusinessPayBill, MerchantToMerchantTransfer, MerchantTransferFromMerchantToWorking, MerchantServicesMMFAccountTransfer, AgencyFloatAdvance
# Amount	The amount being transacted.
# PartyA	Organization’s short code initiating the transaction.
# SenderIdentifier	Type of organization sending the transaction.
# PartyB	Organization’s short code receiving the funds being transacted.
# RecieverIdentifierType	Type of organization receiving the funds being transacted.
# Remarks	Comments that are sent along with the transaction.
# QueueTimeOutURL	The path that stores information of time out transactions.it should be properly validated to make sure that it contains the port, URI and domain name or publicly available IP.
# ResultURL	The path that receives results from M-Pesa it should be properly validated to make sure that it contains the port, URI and domain name or publicly available IP.
# AccountReference	Account Reference mandatory for “BusinessPaybill” CommandID.

# TODO: MPesa Balance interface
# TODO: Automatically create the records for shortcodes once the acquirer is live
# POST https://sandbox.safaricom.co.ke/mpesa/accountbalance/v1/query
# request = { "Initiator":" ",
#       "SecurityCredential":" ",
#       "CommandID":"AccountBalance",
#       "PartyA":"shortcode",
#       "IdentifierType":"4",
#       "Remarks":"Remarks",
#       "QueueTimeOutURL":"https://ip_address:port/timeout_url",
#       "ResultURL":"https://ip_address:port/result_url"
#       }
# Account Balance - Request Parameters
# Parameter	Description
# Initiator	This is the credential/username used to authenticate the transaction request.
# SecurityCredential	Base64 encoded string of the M-Pesa short code and password, which is encrypted using M-Pesa public key and validates the transaction on M-Pesa Core system.
# CommandID	A unique command passed to the M-Pesa system.
# PartyB	The shortcode of the organisation receiving the transaction.
# ReceiverIdentifierType	Type of the organisation receiving the transaction.
# Remarks	Comments that are sent along with the transaction.
# QueueTimeOutURL	The timeout end-point that receives a timeout message.
# ResultURL	The end-point that receives a successful transaction.
# AccountType	Organisation receiving the funds.