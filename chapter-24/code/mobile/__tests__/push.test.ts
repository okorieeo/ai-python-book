it("ignores anything that is not on the allow-list", () => {
  const bad = ["https://evil.example/login", "//evil.example", "/../secret", "/admin",
               "javascript:alert(1)", 5];
  for (const url of bad) expect(routeFromNotificationData({ url })).toBeNull();
  expect(routeFromNotificationData(null)).toBeNull();
  expect(routeFromNotificationData({})).toBeNull();
});

it("treats 404 as success, and any other failure as a failure", async () => {
  const gone = setup(new ApiError(404, "not_found", "Not found."));
  await gone.registrar.register("ExponentPushToken[abc]", "ios", "iPhone");
  await expect(gone.registrar.unregister()).resolves.toBeUndefined();

  const broken = setup(new ApiError(500, "http_error", "boom"));
  await broken.registrar.register("ExponentPushToken[abc]", "ios", "iPhone");
  await expect(broken.registrar.unregister()).rejects.toMatchObject({ status: 500 });
});
