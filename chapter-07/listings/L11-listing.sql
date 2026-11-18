INSERT INTO users (email, name) VALUES ('ada@example.com', 'Ada');
INSERT INTO plans (code, name, price_cents, currency, billing_interval, monthly_token_limit)
VALUES ('pro', 'Pro', 1900, 'USD', 'month', 1000000);

INSERT INTO subscriptions (user_id, plan_id, provider, provider_subscription_id, status)
VALUES (1, 1, 'stripe', 'sub_demo_1', 'active');

-- Try to break the rules. Each of these should FAIL:
INSERT INTO subscriptions (user_id, plan_id, provider, provider_subscription_id, status)
VALUES (1, 1, 'paystack', 'SUB_demo_2', 'active');            -- second live subscription
INSERT INTO plans (code, name, price_cents, currency, billing_interval, monthly_token_limit)
VALUES ('x', 'X', -1, 'USD', 'month', 10);                    -- negative price
DELETE FROM plans WHERE code = 'pro';                         -- protected by a subscription
