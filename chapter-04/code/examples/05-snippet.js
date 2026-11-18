console.log(0.1 + 0.2);          // 0.30000000000000004 (same floating-point issue as Python)
console.log(Number("42") + 1);   // 43  (string -> number)
console.log(parseInt("42px"));   // 42
console.log(Number("abc"));      // NaN (Not a Number)
console.log(Math.round(3.6), Math.max(1, 5, 3));
