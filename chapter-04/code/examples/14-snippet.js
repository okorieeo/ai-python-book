const user = {
  id: 1,
  name: "Ada",
  plan: "free",
  address: { city: "Abuja", country: "NG" },
};

console.log(user.name);            // dot access
console.log(user["plan"]);         // bracket access
user.plan = "pro";                 // update
user.email = "ada@example.com";    // add
delete user.id;                    // remove

console.log(Object.keys(user));    // ["name", "plan", "address", "email"]
console.log(Object.entries(user)); // [["name","Ada"], ...]
