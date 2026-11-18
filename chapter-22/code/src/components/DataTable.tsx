import type { ReactNode } from "react";
import { ui } from "@/lib/ui";

export interface Column<T> {
  key: string;
  header: string;
  sortKey?: string; // the API's ordering name; leave out if not sortable
  align?: "left" | "right";
  render: (row: T) => ReactNode;
}

const alignOf = (col: { align?: "left" | "right" }) =>
  col.align === "right" ? "text-right tabular-nums" : "";

/** A table whose sorting happens on the SERVER: it only reports the click. */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  ordering,
  onOrderingChange,
  dimmed = false,
  empty,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  ordering: string; // "username" ascending, "-username" descending
  onOrderingChange: (next: string) => void;
  dimmed?: boolean; // refreshing: keep showing the old rows, faded
  empty: ReactNode;
}) {
  const sortState = (sortKey?: string) => {
    if (!sortKey) return undefined;
    if (ordering === sortKey) return "ascending";
    if (ordering === `-${sortKey}`) return "descending";
    return "none";
  };

  return (
    <div className={ui.tableWrap}>
      <table className={`w-full text-sm ${dimmed ? "opacity-60" : ""}`}>
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-gray-50 text-left dark:bg-gray-900">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                aria-sort={sortState(col.sortKey)}
                className={`px-3 py-2 font-medium ${alignOf(col)}`}
              >
                {col.sortKey ? (
                  <button
                    onClick={() =>
                      onOrderingChange(
                        ordering === col.sortKey
                          ? `-${col.sortKey}`
                          : col.sortKey!,
                      )
                    }
                    className="inline-flex items-center gap-1 hover:underline"
                  >
                    {col.header}
                    <span aria-hidden="true" className="text-gray-400">
                      {sortState(col.sortKey) === "ascending"
                        ? "▲"
                        : sortState(col.sortKey) === "descending"
                          ? "▼"
                          : "↕"}
                    </span>
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="hover:bg-gray-50 dark:hover:bg-gray-900"
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-3 py-2 ${alignOf(col)}`}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="p-8 text-center text-sm text-gray-500">{empty}</div>
      )}
    </div>
  );
}
