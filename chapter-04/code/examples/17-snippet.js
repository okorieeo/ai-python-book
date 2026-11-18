const text = JSON.stringify({ name: "Ada", skills: ["python", "js"] });
console.log(text);                       // string

const parsed = JSON.parse(text);          // object again
console.log(parsed.skills[0]);

// JSON.parse throws on invalid input - protect it
try {
  JSON.parse("not json");
} catch (error) {
  console.log("Invalid JSON:", error.message);
}
