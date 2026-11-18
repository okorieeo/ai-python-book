def stream_words(text: str):
    for word in text.split():
        yield word + " "

for piece in stream_words("this arrives word by word"):
    print(piece, end="", flush=True)
print()
