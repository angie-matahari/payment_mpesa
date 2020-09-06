# -*- coding: utf-8 -*-

import json
import logging
import pprint
import hashlib
import hmac

import requests
import werkzeug
from werkzeug import urls

from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class MpesaController(http.Controller):
    # FIXME: Sort this out please
    # _access_return_url = '/payment/mpesa/access/'
    _callback_url = '/payment/mpesa/callback/'
    _pay_url = '/payment/mpesa/pay/'
    # _confirm_url = '/payment/mpesa/confirm/'
    _feedback_url = '/payment/mpesa/pay/'
    _return_url = '/payment/mpesa/confirm/'
    _cancel_url = '/payment/mpesa/cancel/'
    _error_url = '/payment/mpesa/error'

    @http.route(
        ['/payment/mpesa/callback/'], type='json', auth='public', methods=['POST'], 
        csrf=False, website=True)
    def mpesa_return(self, **post):
        _logger.info(post)
        checkout_request_id = post.get('CheckoutRequestID', None)
        merchant_request_id = post.get('MerchantRequestID', None)
        
        if checkout_request_id and merchant_request_id:
            request.env['payment.transaction'].sudo().form_feedback(post, 'mpesa')
        return "Success"

    @http.route('/payment/mpesa/confirm/', type='http', website=True)
    def payment_confirmation(self, **post):
        _logger.info(post)
        print(post)
        reference = post['reference']
        if reference:
            tx = request.env['payment.transaction'].sudo().browse(reference)
            # providers = request.env['payment.acquirer'].sudo().search([])
            return request.render("payment_mpesa.mpesa_form", {'reference': reference, 'tx': tx, 'currency': post['currency']})

    @http.route(
        ['/payment/mpesa/pay/'], type='http', auth='public', methods=['POST'], 
        csrf=False)
    def mpesa_pay(self, **post):
        # TODO: Add way to get tx object
        # TODO: Investigate this return_url thing
        # TODO: Add phone capture details
        tx = request.env['payment.transaction'].sudo().search([('reference', '=', post['reference'])], limit=1)
        print(tx.id)
        print(post['reference'])
        # return_url = post['return_url'] or tx.return_url
        print(post['phone'])
        tx.write({'mpesa_tx_phone': post['phone']}) 
        try:
            tx.s2s_do_transaction()
            # secret = request.env['ir.config_parameter'].sudo().get_param('database.secret')
            # token_str = '%s%s%s' % (tx.id, tx.reference, tx.amount)
            # token = hmac.new(secret.encode('utf-8'), token_str.encode('utf-8'), hashlib.sha256).hexdigest()
            # tx.return_url = return_url or '/website_payment/confirm?tx_id=%d&access_token=%s' % (tx.id, token)
        except Exception as e:
            _logger.exception(e)
        # TODO: REDIRECT?
        return werkzeug.utils.redirect('/payment/process')


# TODO: Timeout url
# TODO: ConfirmationURL
# TODO: ValidationURL