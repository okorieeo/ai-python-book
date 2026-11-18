it("reconnects with growing delays, and starts over after a good connection", async () => {
  const { socket, timers, last } = setup();
  socket.start();
  await flush();
  last().drop(); // attempt 0 never opened
  timers.fireNext();
  await flush();
  last().drop(); // attempt 1 never opened
  timers.fireNext();
  await flush();
  last().open(); // finally connected
  last().drop(); // and lost again
  expect(timers.delays).toEqual([1000, 2000, 1000]); // 1000 again: the counter was reset
});

it("gives up on a forbidden close code instead of retrying forever", async () => {
  const { socket, timers, last } = setup();
  socket.start();
  await flush();
  last().open();
  last().drop(4403);
  expect(socket.status).toBe("stopped");
  expect(timers.pending).toHaveLength(0);
});
