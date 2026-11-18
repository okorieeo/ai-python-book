import Link from "next/link";

export default function HomePage() {
  return (
    <section className="flex flex-col items-start gap-6 py-16">
      <h1 className="max-w-2xl text-5xl font-bold tracking-tight">
        Ask your documents anything.
      </h1>
      <p className="max-w-xl text-lg text-zinc-600">
        Upload files, chat with an assistant, and get answers with sources.
      </p>
      <Link
        href="/chat"
        className="rounded-lg bg-blue-600 px-5 py-3 font-medium text-white"
      >
        Start chatting
      </Link>
    </section>
  );
}
