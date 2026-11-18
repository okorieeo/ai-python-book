messages = ["hi", "how are you?"]
messages.append("fine, thanks")      # add at end
messages.insert(0, "start")          # add at position
print(messages[0])                   # first item  -> start
print(messages[-1])                  # last item   -> fine, thanks
print(messages[1:3])                 # slice: items 1 and 2
messages.remove("hi")                # remove by value
last = messages.pop()                # remove and return the last item
print(len(messages))                 # number of items
print("start" in messages)           # True
