# Chapter 4 — JavaScript and TypeScript Essentials: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## TypeScript › Setting up a TypeScript project

**terminal**

```bash
mkdir task-client && cd task-client
pnpm init
pnpm add -D typescript tsx @types/node
mkdir src
```

Edit `package.json` to include `"type": "module"` and these scripts:

**package.json (key parts)**

```
{
  "name": "task-client",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "start": "tsx src/index.ts",
    "typecheck": "tsc --noEmit"
  }
}
```

Create `tsconfig.json`:

**tsconfig.json**

```
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

`strict: true` turns on the full set of safety checks. Always keep it on. `tsx` runs TypeScript files directly during development, and `pnpm typecheck` verifies all types without producing output.

> **In Next.js and Expo**
>
> You will not configure this by hand later: `create-next-app` and `create-expo-app` generate a ready-made `tsconfig.json`. Understanding it now means you will know what those files do.


## Python vs. JavaScript: Quick Reference

| **Concept** | **Python** | **JavaScript / TypeScript** |
|---|---|---|
| Print | `print(x)` | `console.log(x)` |
| Variable | `x = 5` | `const x = 5;` / `let x = 5;` |
| Booleans / null | `True`, `False`, `None` | `true`, `false`, `null`, `undefined` |
| Blocks | Indentation | Curly braces `{}` |
| If / else if | `elif` | `else if` |
| Logic | `and`, `or`, `not` | `&&`, `\|\|`, `!` |
| Function | `def f(a): ...` | `const f = (a) => ...` |
| List / dict | `list`, `dict` | `array`, `object` |
| String formatting | `f"Hi {name}"` | Backtick template with `${name}` |
| Equality | `==` | `===` |
| Classes | `self` | `this` |
| Errors | `try / except` | `try / catch` |
| Package manager | `pip` | `npm` / `pnpm` |
| Types | Optional hints | TypeScript annotations |
