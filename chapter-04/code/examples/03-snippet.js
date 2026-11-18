const user = "Ada";
const tokens = 1250;

console.log(`User ${user} used ${tokens} tokens`);
console.log(`Cost: ${(tokens / 1000 * 0.003).toFixed(4)} USD`);

const prompt = `You are a helpful assistant.
Answer in one sentence.`;      // multi-line string
