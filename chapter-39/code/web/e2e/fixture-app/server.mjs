// A tiny stand-in for "your Next.js app" so the E2E tests in this chapter run anywhere with no build step:
// pricing page -> checkout -> success page that waits for the payment webhook. In the real project the same
// spec runs against `npm run dev`; only baseURL changes. Pure Node, no dependencies.
import http from "node:http";

const state = { status: "none", plan: null };

const page = (body, script = "") => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AI Chat</title></head><body>${body}<script>${script}</script></body></html>`;

const PRICING = page(`
<h1>Choose a plan</h1>
<div id="error" role="alert" hidden></div>
<section><h2>Pro</h2><p>$19.99 per month</p><button data-plan="pro">Choose Pro</button></section>
<section><h2>Team</h2><p>$49.99 per month</p><button data-plan="team">Choose Team</button></section>`, `
const err = document.getElementById("error");
const show = (m) => { err.textContent = m; err.hidden = false; };
document.querySelectorAll("button[data-plan]").forEach((b) => b.addEventListener("click", async () => {
  err.hidden = true;
  try {
    const r = await fetch("/api/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan: b.dataset.plan }) });
    const j = await r.json();
    if (!r.ok) return show(j.message || "Something went wrong.");
    location.href = j.url;
  } catch { show("Could not reach the server. Try again."); }
}));`);

const SUCCESS = page(`<h1>Thanks!</h1><p id="status" role="status">Payment pending…</p>`, `
const el = document.getElementById("status");
const tick = async () => {
  const j = await (await fetch("/api/subscription")).json();
  if (j.status === "active") { el.textContent = (j.plan[0].toUpperCase() + j.plan.slice(1)) + " plan active"; return; }
  if (j.status === "failed") { el.textContent = "Payment failed"; return; }
  setTimeout(tick, 150);
};
tick();`);

const readBody = (req) => new Promise((resolve) => { let d = ""; req.on("data", (c) => (d += c)); req.on("end", () => resolve(d)); });
const json = (res, status, obj) => { res.writeHead(status, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };

export function startServer(port = 0) {
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    if (req.method === "GET" && url.pathname === "/pricing") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(PRICING); }
    if (req.method === "GET" && url.pathname === "/checkout/success") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(SUCCESS); }
    if (req.method === "GET" && url.pathname === "/api/subscription") return json(res, 200, { status: state.status, plan: state.plan });
    if (req.method === "POST" && url.pathname === "/api/checkout") {
      const { plan } = JSON.parse((await readBody(req)) || "{}");
      if (!["pro", "team"].includes(plan)) return json(res, 400, { message: "Unknown plan." });
      state.status = "pending"; state.plan = plan;
      return json(res, 200, { url: `/checkout/success?plan=${plan}` });
    }
    // Test-only controls. Never ship routes like these: they stand in for the provider calling our webhook.
    if (req.method === "POST" && url.pathname === "/__test__/reset") { state.status = "none"; state.plan = null; return json(res, 200, {}); }
    if (req.method === "POST" && url.pathname === "/__test__/deliver-webhook") { state.status = "active"; return json(res, 200, {}); }
    res.writeHead(404); res.end("not found");
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ port: server.address().port, close: () => server.close() })));
}
