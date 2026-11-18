/** Syntax highlighting with Shiki, loaded on demand so it never slows the first page load. */
export async function highlight(code: string, language: string | undefined): Promise<string> {
  const { codeToHtml, bundledLanguages } = await import("shiki");
  const lang = language && language in bundledLanguages ? language : "text";
  return codeToHtml(code, {
    lang,
    themes: { light: "github-light", dark: "github-dark" },
    defaultColor: false, // emit CSS variables, so light/dark switching needs no re-render
  });
}
