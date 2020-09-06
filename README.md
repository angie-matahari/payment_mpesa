COMMAND IDS
TransactionReversal	Reversal for an erroneous C2B transaction. for customer payments

SalaryPayment	Used to send money from an employer to employees e.g. salaries
BusinessPayment	Used to send money from business to customer e.g. refunds

PromotionPayment	Used to send money when promotions take place e.g. raffle winners

AccountBalance	Used to check the balance in a paybill/buy goods account (includes utility, MMF, Merchant, Charges paid account).
Create interface that aggregates mpesa txs by command_id txns filters, actions
Create interface to pull balance

DisburseFundsToBusiness	Transfer of funds from utility to MMF account.
BusinessToBusinessTransfer	Transferring funds from one paybills MMF to another paybills MMF account.
BusinessTransferFromMMFToUtility	Transferring funds from paybills MMF to another paybills utility account.
Create interface that allows you to shuffle stuff around

CustomerPayBillOnline	Used to simulate a transaction taking place in the case of C2B Simulate Transaction or to initiate a transaction on behalf of the customer (STK Push).

TransactionStatusQuery	Used to query the details of a transaction.
FOR ALL TXS

CheckIdentity	Similar to STK push, uses M-Pesa PIN as a service.
To onboard guys

BusinessPayBill	Sending funds from one paybill to another paybill
Customer payment if they have a paybill and is company

BusinessBuyGoods	sending funds from buy goods to another buy goods.
Customer payment if they have a paybill and is company


Also another model with acquirer so that
Okay so we have a model that copies txn and has all the relevant extra data 
    phone number
    c2b, b2b, salary, reversal, 

Need to create mpesa/MMF payment method

Payments buy using vendor payment details
    company with boolean till/paybill till number or paybill with account 
    person with phone number, that is mpesa okay 

    if payment by mpesa, create txn, create mpesa metadata