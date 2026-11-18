// Shared Tailwind classes: change a look in one place (Chapter 19).
export const ui = {
  page:
    "min-h-full bg-gray-50 text-gray-900 " +
    "dark:bg-gray-950 dark:text-gray-100",
  card:
    "rounded-xl border border-gray-200 bg-white p-4 " +
    "dark:border-gray-800 dark:bg-gray-900",
  tableWrap:
    "overflow-x-auto rounded-xl border border-gray-200 " +
    "dark:border-gray-800",
  field:
    "rounded-md border border-gray-300 bg-white px-2 py-1 text-sm " +
    "dark:border-gray-700 dark:bg-gray-900",
  primary:
    "rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white " +
    "disabled:opacity-50",
  secondary:
    "rounded-md border border-gray-300 px-3 py-1 text-sm " +
    "hover:bg-gray-50 disabled:opacity-40 " +
    "dark:border-gray-700 dark:hover:bg-gray-800",
  sidebar:
    "flex w-56 shrink-0 flex-col border-r border-gray-200 p-4 " +
    "dark:border-gray-800",
  empty: "flex h-72 items-center justify-center text-sm text-gray-500",
  skeleton: "animate-pulse rounded bg-gray-100 dark:bg-gray-800",
  navCurrent:
    "bg-blue-50 font-medium text-blue-700 " +
    "dark:bg-blue-950 dark:text-blue-300",
};
