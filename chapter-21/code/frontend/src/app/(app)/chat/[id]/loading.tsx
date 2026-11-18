import { MessageListSkeleton } from "@/features/chat/components/skeletons";

// Shown instantly while the route loads: same shape as the real page, so nothing jumps.
export default function Loading() {
  return (
    <div className="flex h-dvh flex-col">
      <div className="flex-1 overflow-hidden">
        <MessageListSkeleton />
      </div>
    </div>
  );
}
