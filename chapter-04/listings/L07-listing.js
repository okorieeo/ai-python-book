// Destructure an object parameter (very common in React components)
function showUser({ name, plan = "free" }) {
  console.log(`${name} is on ${plan}`);
}
showUser({ name: "Ada" });

// Rest parameters (Python's *args)
function sum(...numbers) {
  return numbers.reduce((a, b) => a + b, 0);
}
console.log(sum(1, 2, 3)); // 6
