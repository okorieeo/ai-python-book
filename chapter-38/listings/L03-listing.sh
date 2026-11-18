KEY=$(python -c "import uuid; print(uuid.uuid4())")
curl -s -X POST http://localhost:8000/api/v1/payments/checkout/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" \
  -d '{"plan_code": "pro", "currency": "NGN", "country": "NG"}'
# expected shape: {"payment_id": "pay_...", "provider": "paystack", "redirect_url": "https://checkout.paystack.com/..."}

# the same key again must return the SAME payment_id (no second payment is created)
curl -s -X POST http://localhost:8000/api/v1/payments/checkout/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" -d '{"plan_code": "pro", "currency": "NGN", "country": "NG"}'

# after paying, poll the status
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/payments/pay_.../
# expected: {"status": "succeeded", "amount_minor": ..., "currency": "NGN"}
