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

    @http.route('/payment/mpesa/confirm/', type='http', website=True, auth='public')
    def payment_confirmation(self, **post):
        _logger.info(post)
        print(post)
        reference = post['reference']
        if reference:
            tx = request.env['payment.transaction'].sudo().browse(reference)
            return request.render("payment_mpesa.mpesa_form", {'reference': reference, 'tx': tx, 'currency': post['currency']})

    @http.route(
        ['/payment/mpesa/pay/'], type='http', auth='public', methods=['POST'], 
        csrf=True)
    def mpesa_pay(self, **post):
        reference = post['reference']
        if reference:
            tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)], limit=1)
            tx.write({'mpesa_tx_phone': post['phone']}) 
            try:
                tx.s2s_do_transaction()
            except Exception as e:
                _logger.exception(e)

            return request.render("payment_mpesa.mpesa_complete", {'reference': reference,'tx': tx})

    @http.route(
        ['/payment/mpesa/complete'], type='http', auth='public', methods=['POST'], 
        csrf=True)
    def mpesa_complete(self, **post):
        reference = post['reference']
        if reference:
           tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)], limit=1) 
           status = tx._mpesa_s2s_get_tx_status()
           if status:
               return werkzeug.utils.redirect('/payment/process')
        return request.render("payment_mpesa.mpesa_complete", {'reference': reference, 'tx': tx})
