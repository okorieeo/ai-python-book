import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import hero from "@/assets/hero.png";

export default function HomePage() {
  return (
    <section className="grid items-center gap-10 py-8 md:grid-cols-2 md:py-16">
      <div className="flex flex-col items-start gap-6">
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
          Ask your documents anything.
        </h1>
        <p className="text-muted-foreground max-w-xl text-lg">
          Upload files, chat with an assistant, and get answers with sources.
        </p>
        <Button asChild size="lg">
          <Link href="/chat">Start chatting</Link>
        </Button>
      </div>
      {/* A static import gives next/image the size, so nothing jumps while it loads. */}
      <Image
        src={hero}
        alt="A chat window with a conversation list on the left and a message box at the bottom"
        priority
        sizes="(min-width: 768px) 50vw, 100vw"
        className="rounded-xl border shadow-md"
      />
    </section>
  );
}
