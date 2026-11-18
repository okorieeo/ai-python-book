// utils/cost.js
export function calculateCost(tokens) {
  return (tokens / 1000) * 0.003;
}

export const MAX_TOKENS = 4000;

export default function formatMoney(amount) {   // one default export per file
  return "$" + amount.toFixed(2);
}

// main.js
import formatMoney, { calculateCost, MAX_TOKENS } from "./utils/cost.js";
import * as React from "react";                  // everything from a package

console.log(formatMoney(calculateCost(MAX_TOKENS)));
