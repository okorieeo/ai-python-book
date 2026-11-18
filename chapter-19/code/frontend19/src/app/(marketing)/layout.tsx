import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between py-4">
        <Link href="/" className="text-lg font-bold">
          {process.env.NEXT_PUBLIC_APP_NAME ?? "Chat App"}
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 sm:gap-2">
          <Button asChild variant="ghost">
            <Link href="/pricing">Pricing</Link>
          </Button>
          <Button asChild>
            <Link href="/chat">Open app</Link>
          </Button>
          <ThemeToggle />
        </nav>
      </header>
      <main id="main" className="flex-1 py-8">
        {children}
      </main>
    </div>
  );
}
