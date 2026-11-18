import { ManualNetwork, wireConnectivity } from "../src/network";
import type { OfflineQueue } from "../src/offlineQueue";
import type { SocketManager } from "../src/socket";

function parts() {
  const queue = { flush: jest.fn().mockResolvedValue(undefined) } as unknown as OfflineQueue;
  const socket = { setOnline: jest.fn() } as unknown as SocketManager;
  return { queue, socket };
}

test("coming back online sends what is waiting and wakes the socket", () => {
  const net = new ManualNetwork(false);
  const p = parts();
  wireConnectivity(net, p);
  net.set(true);
  expect(p.queue.flush).toHaveBeenCalledTimes(1);
  expect(p.socket.setOnline).toHaveBeenCalledWith(true);
});

test("going offline tells the socket but sends nothing", () => {
  const net = new ManualNetwork(true);
  const p = parts();
  wireConnectivity(net, p);
  net.set(false);
  expect(p.queue.flush).not.toHaveBeenCalled();
  expect(p.socket.setOnline).toHaveBeenCalledWith(false);
});

test("stopping the wiring stops the reactions", () => {
  const net = new ManualNetwork(false);
  const p = parts();
  const stop = wireConnectivity(net, p);
  stop();
  net.set(true);
  expect(p.queue.flush).not.toHaveBeenCalled();
});

test("either part is optional", () => {
  const net = new ManualNetwork(false);
  wireConnectivity(net, {});
  expect(() => net.set(true)).not.toThrow();
});
