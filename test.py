import uuid

from yookassa import Configuration, Payment

Configuration.account_id = 1218211
Configuration.secret_key = "test_VWfSLEpLv-YHWCCXYQSP-M1dNrvdcWf_Ic3HLWdltvU"

payment = Payment.create({
    "amount": {
        "value": "100.00",
        "currency": "RUB"
    },
    "confirmation": {
        "type": "redirect",
        "return_url": "https://www.example.com/return_url"
    },
    "capture": True,
    "description": "Заказ №1"
}, uuid.uuid4())

print(payment.confirmation.confirmation_url)