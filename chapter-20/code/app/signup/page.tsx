import { SignupForm } from "@/components/forms/SignupForm";

export default function SignupPage() {
  return (
    <main>
      <SignupForm />
      <p>Already registered? <a href="/login">Log in</a></p>
    </main>
  );
}
