"""Rank a feature backlog with RICE scoring and group it with MoSCoW labels."""

# reach: users affected per quarter | impact: 0.25 minimal, 0.5 low, 1 medium, 2 high, 3 massive
# confidence: 0.5 to 1.0 (how sure are we?) | effort: person-weeks | moscow: must/should/could/wont
BACKLOG = [
    {"name": "Email sign-up and login",           "reach": 1000, "impact": 3,    "confidence": 1.0, "effort": 2,   "moscow": "must"},
    {"name": "Streaming chat with the assistant", "reach": 1000, "impact": 3,    "confidence": 0.8, "effort": 4,   "moscow": "must"},
    {"name": "Conversation history",              "reach": 900,  "impact": 2,    "confidence": 1.0, "effort": 1.5, "moscow": "must"},
    {"name": "Plans, limits and usage meter",     "reach": 1000, "impact": 2,    "confidence": 0.8, "effort": 3,   "moscow": "must"},
    {"name": "Stripe and Paystack subscriptions", "reach": 400,  "impact": 3,    "confidence": 0.8, "effort": 5,   "moscow": "must"},
    {"name": "Mobile app (React Native)",         "reach": 700,  "impact": 2,    "confidence": 0.8, "effort": 6,   "moscow": "should"},
    {"name": "Document Q&A (RAG)",                "reach": 300,  "impact": 2,    "confidence": 0.5, "effort": 6,   "moscow": "could"},
    {"name": "Social login (Google)",             "reach": 600,  "impact": 1,    "confidence": 0.8, "effort": 1,   "moscow": "should"},
    {"name": "Dark mode",                         "reach": 500,  "impact": 0.5,  "confidence": 1.0, "effort": 0.5, "moscow": "could"},
    {"name": "Team workspaces",                   "reach": 100,  "impact": 2,    "confidence": 0.5, "effort": 8,   "moscow": "wont"},
]

for item in BACKLOG:
    item["rice"] = item["reach"] * item["impact"] * item["confidence"] / item["effort"]

print(f"{'#':>2}  {'Feature':<36} {'RICE':>7}  {'Effort':>6}  MoSCoW")
for rank, item in enumerate(sorted(BACKLOG, key=lambda i: i["rice"], reverse=True), start=1):
    print(f"{rank:>2}  {item['name']:<36} {item['rice']:>7.0f}  {item['effort']:>4}w   {item['moscow']}")

mvp = [i for i in BACKLOG if i["moscow"] == "must"]
print(f"\nMVP (the 'must' items): {len(mvp)} features, {sum(i['effort'] for i in mvp):g} person-weeks")
later = [i["name"] for i in BACKLOG if i["moscow"] in ("should", "could")]
print("After launch:", "; ".join(later))
print("Not now:", "; ".join(i["name"] for i in BACKLOG if i["moscow"] == "wont"))
