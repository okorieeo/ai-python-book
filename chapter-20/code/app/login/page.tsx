import { Suspense } from "react";
import { LoginForm } from "@/components/forms/LoginForm";

export default function LoginPage() {
  // useSearchParams() inside LoginForm requires a Suspense boundary
  return (
    <main>
      <Suspense fallback={<p>Loading...</p>}>
        <LoginForm />
      </Suspense>
      <p>No account? <a href="/signup">Create one</a></p>
    </main>
  );
}
