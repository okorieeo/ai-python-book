import { spawn } from "node:child_process";

/** Start the Python mock backend on a port and wait until it is listening. */
export async function startMock(port: number, env: Record<string, string> = {}): Promise<{ stop: () => void }> {
  const script = new URL("../../tools/mock_backend/mock_backend.py", import.meta.url).pathname;
  const child = spawn("python3", [script], { env: { ...process.env, PORT: String(port), ...env }, stdio: ["ignore", "pipe", "inherit"] });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("mock backend did not start")), 8000);
    child.stdout!.on("data", (chunk: Buffer) => {
      if (String(chunk).includes("Mock backend")) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.on("error", reject);
  });
  return { stop: () => child.kill() };
}

export const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
