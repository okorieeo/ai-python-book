const user = { name: "Ada", profile: null };

// Without ?.  -> user.profile.city would crash (cannot read property of null)
console.log(user.profile?.city);            // undefined (safe)
console.log(user.profile?.city ?? "unknown"); // "unknown"  (default only for null/undefined)

const count = 0;
console.log(count || 10);   // 10  (|| treats 0 as false - often a bug)
console.log(count ?? 10);   // 0   (?? only replaces null/undefined)
