import { formatNumber } from "@/lib/format";
import { ui } from "@/lib/ui";

export function Pagination({
  page,
  pageSize,
  count,
  onPage,
}: {
  page: number;
  pageSize: number;
  count: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(Math.ceil(count / pageSize), 1);
  const first = count === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, count);
  const button = ui.secondary;
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between py-3 text-sm"
    >
      <p aria-live="polite" className="text-gray-500">
        Showing {formatNumber(first)}–{formatNumber(last)} of{" "}
        {formatNumber(count)}
      </p>
      <div className="flex items-center gap-2">
        <button
          className={button}
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <span className="text-gray-500">
          Page {page} of {pages}
        </span>
        <button
          className={button}
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
