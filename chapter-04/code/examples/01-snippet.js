const name = "Ada";        // cannot be reassigned (use by default)
let attempts = 0;          // can be reassigned
attempts = attempts + 1;
attempts += 1;

// name = "Bo";            // Error: Assignment to constant variable

console.log(name, attempts);
