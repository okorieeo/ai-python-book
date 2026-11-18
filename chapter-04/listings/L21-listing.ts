function greet(name: string, times: number = 1): string {
  return ("Hello " + name + "! ").repeat(times).trim();
}

const double = (n: number): number => n * 2;

// A function type: used for callbacks and React props
type Handler = (message: string) => void;
const logger: Handler = (m) => console.log(m);

// async functions return Promise<T>
async function fetchName(id: number): Promise<string> {
  return "Ada";
}
