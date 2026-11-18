# Traditional: deterministic, you write the exact rules
def is_spam(email_text: str) -> bool:
    spam_words = ["free money", "winner", "click here now"]
    return any(word in email_text.lower() for word in spam_words)

# AI-powered: you describe the goal, the model uses its understanding of language
def is_spam_ai(email_text: str) -> bool:
    answer = ask_model(
        "Reply with only YES or NO. Is this email spam?\n\n" + email_text
    )
    return answer.strip().upper() == "YES"
