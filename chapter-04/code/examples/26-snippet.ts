// JavaScript: this bug is found only when the code runs (or never)
function total(price, quantity) { return price * quantity; }
total("10", "abc");           // NaN, no warning

// TypeScript: caught immediately in the editor
function total(price: number, quantity: number): number {
  return price * quantity;
}
total("10", "abc");           // Error: Argument of type 'string' is not assignable to 'number'
