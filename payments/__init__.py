# PayU payment-first booking flow.
#
# payu_client.py   — PayU API: payment link creation, webhook hash verification
# templates.py     — WhatsApp message templates (payment request / payment confirmed)
# payment_flow.py  — orchestration: send bill+link → wait for payment → Djubo booking + confirmation
