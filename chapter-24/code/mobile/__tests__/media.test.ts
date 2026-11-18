it("reports blocked, without asking, when the system will not show its dialog", async () => {
  const request = jest.fn();
  expect(await ensurePermission(async () => never, request)).toBe("blocked");
  expect(request).not.toHaveBeenCalled();
});

it("reports blocked when the person chooses Don't ask again", async () => {
  expect(await ensurePermission(async () => no, async () => never)).toBe("blocked");
});
// ----- next listing from the chapter -----
it("refuses anything over the server limit, and says how big it was", () => {
  const verdict = validateAsset({
    uri: "file:///a.jpg",
    mimeType: "image/jpeg",
    fileSize: MAX_UPLOAD_BYTES + 1,
  });
  expect(verdict.ok).toBe(false);
  expect(!verdict.ok && verdict.message).toMatch(/10\.0 MB.*limit is 10 MB/);
});

it("describes the file as {uri, name, type}, the React Native way", () => {
  // ...with a FakeForm that records append()
  expect(appended).toEqual([
    ["file", { uri: "file:///cache/a.jpg", name: "invoice.jpg", type: "image/jpeg" }],
  ]);
});
