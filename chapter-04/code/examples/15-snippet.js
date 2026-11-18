const { name, plan } = user;                    // pull out properties
const { address: { city } } = user;               // nested
const [first, second] = ["a", "b", "c"];          // arrays by position

console.log(name, plan, city, first, second);
