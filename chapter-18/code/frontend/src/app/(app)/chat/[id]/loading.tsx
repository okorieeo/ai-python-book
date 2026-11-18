export default function Loading() {
  return (
    <div className="flex h-full flex-col gap-3 p-4" aria-busy="true">
      <div className="h-10 w-2/3 animate-pulse rounded-2xl bg-zinc-100" />
      <div className="ml-auto h-10 w-1/2 animate-pulse rounded-2xl bg-zinc-100" />
      <div className="h-10 w-3/5 animate-pulse rounded-2xl bg-zinc-100" />
    </div>
  );
}
