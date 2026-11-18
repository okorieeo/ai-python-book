import type { Config } from "jest";
import nextJest from "next/jest.js";

// next/jest wires up the compiler, CSS and image stubs and .env loading for you.
const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  coverageProvider: "v8",
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/e2e/"],    // Playwright specs are NOT Jest tests
};

export default createJestConfig(config);
