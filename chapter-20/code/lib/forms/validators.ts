/** Pure validation helpers, shared by the Zod schemas and by unit tests. The server (Django validators) stays authoritative. */
export function isValidEmail(value: string): boolean {
  const email = value.trim();
  return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
}

const COMMON_PASSWORDS = new Set(["password", "12345678", "123456789", "qwertyui", "iloveyou", "11111111", "password1"]);

/** Return a list of human-readable problems; an empty list means the password looks acceptable. */
export function passwordProblems(password: string, email = ""): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push("Use at least 8 characters.");
  if (password.length > 128) problems.push("Use 128 characters or fewer.");
  if (password.length > 0 && /^\d+$/.test(password)) problems.push("Don\u2019t use only numbers.");
  if (COMMON_PASSWORDS.has(password.toLowerCase())) problems.push("That password is too common.");
  const local = email.split("@")[0]?.toLowerCase() ?? "";
  if (local.length >= 4 && password.toLowerCase().includes(local)) problems.push("Don\u2019t include your email name in the password.");
  return problems;
}
