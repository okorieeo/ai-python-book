import { formatNumber } from "@/lib/format";
import type { TopUser } from "@/lib/types";

export function TopUsersList({ users }: { users: TopUser[] }) {
  const max = Math.max(...users.map((u) => u.tokens), 1);
  return (
    <ol className="space-y-3">
      {users.map((user) => (
        <li key={user.username}>
          <div className="flex justify-between text-sm">
            <span className="font-medium">{user.username}</span>
            <span className="tabular-nums text-gray-500">
              {formatNumber(user.tokens)}
            </span>
          </div>
          <div className="mt-1 h-2 rounded bg-gray-100 dark:bg-gray-800">
            <div
              className="h-2 rounded bg-blue-600"
              style={{ width: `${(user.tokens / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}
