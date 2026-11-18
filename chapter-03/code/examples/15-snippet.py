text = "  Summarize THIS document, please.  "
clean = text.strip().lower()
words = clean.split()
print(len(words), "words")
print(" ".join(words[:2]))
