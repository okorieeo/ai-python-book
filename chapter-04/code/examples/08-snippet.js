// classic for loop
for (let i = 0; i < 3; i++) {
  console.log(i);
}

// for...of: loop over values (preferred for arrays)
const models = ["fast", "balanced", "smart"];
for (const model of models) {
  console.log(model);
}

// for...in loops over object KEYS
const plan = { name: "pro", price: 29 };
for (const key in plan) {
  console.log(key, plan[key]);
}

// while
let n = 0;
while (n < 3) {
  n++;
}
