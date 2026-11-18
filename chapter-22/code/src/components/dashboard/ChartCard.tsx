import type { ReactNode } from "react";
import { ui } from "@/lib/ui";

export interface DataTable {
  caption: string;
  headers: string[];
  rows: (string | number)[][];
}

type State = "loading" | "error" | "empty" | "ready";

/** Every chart has four honest states, plus a table for screen readers. */
export function ChartCard({
  title,
  description,
  state,
  onRetry,
  actions,
  table,
  children,
}: {
  title: string;
  description?: string;
  state: State;
  onRetry?: () => void;
  actions?: ReactNode;
  table?: DataTable;
  children?: ReactNode;
}) {
  return (
    <section className={ui.card}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {description && (
            <p className="text-sm text-gray-500">{description}</p>
          )}
        </div>
        {actions}
      </header>

      {state === "loading" && (
        <div
          role="status"
          aria-label={`Loading ${title}`}
          className="h-72 animate-pulse rounded bg-gray-100 dark:bg-gray-800"
        />
      )}
      {state === "error" && (
        <div
          role="alert"
          className="flex h-72 flex-col items-center justify-center gap-3"
        >
          <p className="text-sm text-gray-600 dark:text-gray-300">
            We could not load this chart.
          </p>
          {onRetry && (
            <button onClick={onRetry} className={ui.secondary}>
              Try again
            </button>
          )}
        </div>
      )}
      {state === "empty" && (
        <p className={ui.empty}>No data for this period yet.</p>
      )}
      {state === "ready" && (
        <>
          <div role="img" aria-label={`${title}. ${description ?? ""}`}>
            {children}
          </div>
          {table && (
            <table className="sr-only">
              <caption>{table.caption}</caption>
              <thead>
                <tr>
                  {table.headers.map((h) => (
                    <th key={h} scope="col">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
