plan = "pro"
tokens_used = 9500
limit = 10000

if tokens_used >= limit:
    print("Limit reached. Please upgrade.")
elif tokens_used >= limit * 0.8:
    print("Warning: you used over 80% of your tokens.")
else:
    print("All good.")

# Conditional expression (one-line if)
label = "Premium" if plan == "pro" else "Free"
