console.log("1. start");
setTimeout(() => console.log("2. finished waiting"), 1000);
console.log("3. end");

// Output order: 1. start, 3. end, 2. finished waiting
