python manage.py billing_demo

1. The pricing table (prices in the smallest unit, shown formatted)
   free        $0.00        ₦0.00     30 messages/month  agent tools: False
   starter     $5.00    ₦7,500.00    300 messages/month  agent tools: True
   pro        $29.00   ₦45,000.00   1500 messages/month  agent tools: True

2. Ada on the Free plan runs into her limit
   model for Ada: claude-haiku-5-5
   31st message refused: limit 30, used 30

3. Ada subscribes to Starter on 1 Feb, then upgrades to Pro halfway through
   period: 01 Feb to 01 Mar, status active
   upgrade now: credit $2.50 for unused Starter, charge $14.50 for the rest on Pro, net $12.00
     Invoice INV-2026-000001
       Unused time on Starter  x1  -$2.50
       Remaining time on Pro  x1  $14.50
       Tax: $0.00
       Total: $12.00

4. A month of heavy use on Pro, then the renewal invoice with 7.5% tax (an example rate)
   usage: 1650 of 1500 included
     Invoice INV-2026-000002
       Pro (monthly)  x1  $29.00
       Extra AI messages: 150 over 1500, in blocks of 100  x2  $3.00
       Tax: $2.40
       Total: $34.40
   payment recorded: True; the same payment message arriving again was recorded: False
   invoice status: paid

5. What the signed-in user sees at GET /api/v1/billing/me/ (Ben, on Pro since just now)
   plan: {'code': 'pro', 'name': 'Pro'}
   status: active, cancel at period end: False
   entitlements: ai.chat=True, ai.agent_tools=True, ai.premium_models=True, ai.messages_per_month=1500, chat.max_conversations=unlimited
   usage: 0 used, 1500 remaining of 1500

6. Unit economics: does each plan make money? (example fee 2.9% + 30 cents; model costs from Chapter 27)
   plan    model                  price  cost @40%  margin @40%  cost @100%  margin @100%
   starter claude-haiku-5-5       $5.00      $0.06          90%       $0.16           88%
   pro     claude-sonnet-5-5     $29.00      $6.51          74%      $16.27           40%
   free     claude-haiku-5-5   costs $0.0162 per user per month at full use, so 1,000 such users cost $16.20

(everything above was rolled back: no data was kept)
