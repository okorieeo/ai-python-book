import { z } from "zod";

// Client-side validation is for the person typing, not for security (17.1):
// the server checks everything again. Keep these rules in step with the Django serializer.
export const loginSchema = z.object({
  email: z.string().trim().min(1, "Enter your email address").pipe(z.email("Enter a valid email address")),
  // No complexity rules at login: the server decides, and says the same thing for every failure.
  password: z.string().min(1, "Enter your password"),
});

export type LoginValues = z.infer<typeof loginSchema>;
