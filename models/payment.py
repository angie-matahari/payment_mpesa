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
        environment = self._get_mpesa_environment()
        if environment == 'prod':
            return {
                'mpesa_form_url': '/payment/mpesa/confirm/',
                'access_token': 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials',
                'stk_push': 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest', # CustomerPayBillOnline
                'stk_push_status': 'https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query' 
            }
        return {
            'mpesa_form_url': '/payment/mpesa/confirm/',
            'access_token': 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials',
            'stk_push': 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest',
            'stk_push_status': 'https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query'
        }

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
        
        if auth:
            url = self._get_mpesa_urls()['access_token']
            response = requests.get(url, auth=HTTPBasicAuth(
                self.mpesa_customer_key, self.mpesa_secrete_key))
            json_data = json.loads(response.text)
            # TODO: Handle not successful scenarios as well
            return json_data['access_token']

        url = self._get_mpesa_urls()[values['url']]
        headers = {
            'Authorization': 'Bearer %s' % self._mpesa_get_access_token()
            }
        data = self._mpesa_get_stk_request_data(values)
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
    def _mpesa_get_stk_request_data(self, values):
        self.ensure_one()
        base_url = self.get_base_url()

        time_stamp = str(time.strftime('%Y%m%d%H%M%S'))
        passkey = self.mpesa_short_code + self.mpesa_pass_key + time_stamp
        password = str(base64.b64encode(passkey.encode('utf-8')), 'utf-8')
        if values['url'] == 'stk_push':
            # TODO: Remove url from the values
            values.update({
                "BusinessShortCode": self.mpesa_short_code,
                "Password": password,
                "Timestamp": time_stamp,
                "PartyB": self.mpesa_short_code,
                "CallBackURL": 'https://demo13.kylix.online/payment/mpesa/callback/',
            })
        elif values['url'] == 'stk_push_status':
            values.update({
                "BusinessShortCode": self.mpesa_short_code,
                "Password": password,
                # FIXME: Is this the current time_stamp or that of tx 
                "Timestamp": time_stamp,
            })
        return values
    
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
        return values

    @api.depends('amount', 'currency_id')
    def _compute_mpesa_amount_currency(self):
        for tx in self:
            tx.mpesa_amount = tx.amount

    def _mpesa_get_request_data(self, **options):
        self.ensure_one()
        if options.get('pay', False):
            if self.mpesa_pos_tx:
               return {
                "url": 'stk_push',
                "TransactionType": 'CustomerPayBillOnline',
                "Amount": self.mpesa_amount,
                "PartyA": self.mpesa_tx_phone,
                "PhoneNumber": self.mpesa_tx_phone,
                "AccountReference": self.pos_order_id.display_name,
                "TransactionDesc": self.reference
            } 
            return {
                "url": 'stk_push',
                "TransactionType": self.mpesa_command_id,
                "Amount": 10,
                "PartyA": self.mpesa_tx_phone,
                "PhoneNumber": self.mpesa_tx_phone,
                "AccountReference": self.partner_name,
                "TransactionDesc": self.reference
            }
        
        elif options.get('stk_status', False):
            return {
                "url": 'stk_push_status',
                "CheckoutRequestID": self.checkout_request_id
            }

    def mpesa_s2s_do_transaction(self, **data):
        self.ensure_one()
        values = self._mpesa_get_request_data(pay=True)
        response = self.acquirer_id.mpesa_request(values)
        # TODO: Change this validate to check for different things
        return self._mpesa_s2s_validate(response)

    def _mpesa_s2s_validate(self, data):
        # TODO: set txns with already returned stuff from acquirer
        _logger.info(data)
        # status = data['Body']['stkCallback'].get('ResultCode')
        status = data.get('ResponseCode')
        # TODO: Get errorCode and errorMessage from response
        # error = data.get('errorCode')
        _logger.info(status)
        if status == '0':
            _logger.info('status 0')
            _logger.info('pending')
            self.write({'state_message': data.get('ResponseDescription'),
                        'checkout_request_id': data.get('CheckoutRequestID'),
                        'merchant_request_id': data.get('MerchantRequestID'),
            })
            return True
        return False

    def _mpesa_s2s_get_tx_status(self):
        self.ensure_one()
        values = self._mpesa_get_request_data(stk_status=True)
        response = self.acquirer_id.mpesa_request(values)
        self.form_feedback(response, 'mpesa')
        if self.state == 'done':
            return True
        return False

    @api.model
    def _mpesa_form_get_tx_from_data(self, data):
        checkout_request_id = data.get('CheckoutRequestID')
        if not checkout_request_id:
            error_msg = _('Mpesa: received data with missing reference (%s)') % (checkout_request_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

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
        if not data.get('ResultCode'):
            invalid_parameters.append(('ResultCode', data.get('ResultCode'), '0'))
        return invalid_parameters

    def _mpesa_form_validate(self, data):
        result_code = data.get('ResultCode')
        if result_code == 0:
            self._set_transaction_done()
        elif result_code == 1032:
            self._set_transaction_cancel()
       