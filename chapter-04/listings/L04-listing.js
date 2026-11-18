const messages = ["hi", "how are you?"];
messages.push("fine");              // add to end
messages.unshift("start");          // add to start
console.log(messages[0]);           // "start"
console.log(messages.at(-1));       // "fine" (last item)
console.log(messages.length);       // 3
console.log(messages.includes("hi")); // true
const removed = messages.pop();     // remove and return last
const part = messages.slice(1, 3);  // copy of a section (original unchanged)
