import { z } from "zod";
import { isValidEmail, passwordProblems } from "./validators";

const email = z
  .string()
  .trim()
  .min(1, "Enter your email.")
  .refine(isValidEmail, "Enter an email like name@example.com.");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const signupSchema = z
  .object({
    name: z.string().trim().min(1, "Enter your name.").max(100, "Use 100 characters or fewer."),
    email,
    password: z.string(),
    confirmPassword: z.string(),
  })
  .superRefine((values, ctx) => {
    for (const message of passwordProblems(values.password, values.email)) {
      ctx.addIssue({ code: "custom", path: ["password"], message });
    }
    if (values.password !== values.confirmPassword) {
      ctx.addIssue({ code: "custom", path: ["confirmPassword"], message: "Passwords do not match." });
    }
  });
export type SignupValues = z.infer<typeof signupSchema>;

export const conversationSchema = z.object({
  title: z.string().trim().min(1, "Enter a title.").max(200, "Use 200 characters or fewer."),
});
export type ConversationValues = z.infer<typeof conversationSchema>;
