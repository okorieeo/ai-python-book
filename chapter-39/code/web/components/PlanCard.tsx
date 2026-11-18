import { formatMoney } from "../lib/format";

interface Props {
  name: string;
  priceMinor: number;
  currency: string;
  features: string[];
  loading?: boolean;
  onChoose: (plan: string) => void;
}

export function PlanCard({ name, priceMinor, currency, features, loading = false, onChoose }: Props) {
  return (
    <section aria-labelledby={`plan-${name}`}>
      <h2 id={`plan-${name}`}>{name}</h2>
      <p>{formatMoney(priceMinor, currency)} per month</p>
      <ul>{features.map((f) => <li key={f}>{f}</li>)}</ul>
      <button type="button" disabled={loading} onClick={() => onChoose(name.toLowerCase())}>
        {loading ? "Redirecting…" : `Choose ${name}`}
      </button>
    </section>
  );
}
