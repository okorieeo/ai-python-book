// function declaration
function calculateCost(tokens, pricePer1k = 0.003) {
  return (tokens / 1000) * pricePer1k;
}

// arrow function (most common in modern code)
const calculateCost2 = (tokens, pricePer1k = 0.003) => (tokens / 1000) * pricePer1k;

// arrow with a body
const greet = (name) => {
  const message = `Hello, ${name}!`;
  return message;
};

console.log(calculateCost(2500));
console.log(greet("Ada"));
