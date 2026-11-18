let userName: string = "Ada";
let age: number = 28;
let isActive: boolean = true;
let tags: string[] = ["ai", "python"];           // array of strings
let scores: Array<number> = [1, 2, 3];           // same idea, other syntax
let pair: [string, number] = ["Ada", 28];        // tuple

// TypeScript infers types, so you often do not need to write them:
const city = "Abuja";          // inferred as string
const count = 5;               // inferred as number
