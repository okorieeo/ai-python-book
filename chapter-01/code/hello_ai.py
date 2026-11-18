import os
from anthropic import Anthropic

# 1. Create a client. It reads your key from the environment variable.
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def ask(question: str) -> str:
    """Send one question to the model and return its text answer."""
    response = client.messages.create(
        model="claude-sonnet-5-5",   # which model to use
        max_tokens=500,               # maximum length of the answer
        system="You are a friendly mentor who explains things to beginners in simple language.",
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text

if __name__ == "__main__":
    print(ask("In three sentences, what does a backend developer do?"))
# ----- next listing from the chapter -----
def chat():
    history = []   # grows with every turn
    print("Chat started. Type 'quit' to stop.\n")

    while True:
        user_text = input("You: ").strip()
        if user_text.lower() == "quit":
            break

        history.append({"role": "user", "content": user_text})

        response = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=500,
            system="You are a friendly mentor who explains things to beginners in simple language.",
            messages=history,          # send the full conversation every time
        )
        answer = response.content[0].text
        history.append({"role": "assistant", "content": answer})

        print(f"AI: {answer}\n")

if __name__ == "__main__":
    chat()
