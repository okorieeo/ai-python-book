import { useEffect, useRef, useState } from "react";
import type { LiveReading } from "./types";

const WS = process.env.NEXT_PUBLIC_WS_URL!;
const KEEP = 120;                       // points kept per sensor: enough for a sparkline, small enough to never grow

export type Series = Record<number, { ts: number; value: number }[]>;

/** Live readings for one farm. Reconnects with exponential backoff and jitter, so a restart of the server does not
 *  make thousands of dashboards reconnect in the same second. */
export function useLiveReadings(farmId: number) {
  const [series, setSeries] = useState<Series>({});
  const [connected, setConnected] = useState(false);
  const attempt = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(`${WS}/ws/farms/${farmId}/live/`);          // the session cookie authenticates the socket
      socket.onopen = () => { attempt.current = 0; setConnected(true); };
      socket.onmessage = (msg) => {
        const r: LiveReading = JSON.parse(msg.data);
        if (r.type !== "reading") return;
        setSeries((prev) => {
          const list = [...(prev[r.sensor_id] ?? []), { ts: Date.parse(r.ts), value: r.value }];
          return { ...prev, [r.sensor_id]: list.slice(-KEEP) };
        });
      };
      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        const delay = Math.min(30000, 1000 * 2 ** attempt.current++) * (0.5 + Math.random() / 2);
        timer = setTimeout(connect, delay);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); socket?.close(); };
  }, [farmId]);

  return { series, connected };
}
