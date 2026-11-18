import Link from "next/link";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-6">
      <header className="flex items-center justify-between py-6">
        <Link href="/" className="text-lg font-bold">
          {process.env.NEXT_PUBLIC_APP_NAME ?? "Chat App"}
        </Link>
        <nav className="flex gap-4 text-sm">
          <Link href="/pricing">Pricing</Link>
          <Link href="/chat" className="font-medium text-blue-600">
            Open app
          </Link>
        </nav>
      </header>
      <main className="flex-1 py-8">{children}</main>
    </div>
  );
}
