const tokensUsed = 9500;
const limit = 10000;

if (tokensUsed >= limit) {
  console.log("Limit reached");
} else if (tokensUsed >= limit * 0.8) {
  console.log("Warning: over 80% used");
} else {
  console.log("All good");
}

const label = tokensUsed > 5000 ? "heavy user" : "light user"; // ternary
