import type { LiveEvent } from "../api/types";

export interface MockEventStream {
  start: () => void;
  pause: () => void;
  resume: () => void;
  stop: () => void;
}

export interface MockEventStreamOptions {
  events: LiveEvent[];
  intervalMs: number;
  onEvent: (event: LiveEvent) => void;
  /** Replay from the top when the script runs out. Default false. */
  loop?: boolean;
}

/* Scripted stand-in for the real SSE stream (GET /api/events/stream).
   Emits the next fixture event on every tick; swapping in the real
   EventSource later replaces this object, not its consumers. */
export function createMockEventStream(options: MockEventStreamOptions): MockEventStream {
  const { events, intervalMs, onEvent, loop = false } = options;
  let timer: ReturnType<typeof setInterval> | null = null;
  let cursor = 0;
  let paused = false;

  const tick = () => {
    if (paused || events.length === 0) {
      return;
    }
    onEvent(events[cursor]);
    cursor += 1;
    if (cursor >= events.length) {
      if (loop) {
        cursor = 0;
      } else {
        stop();
      }
    }
  };

  const start = () => {
    if (timer === null) {
      timer = setInterval(tick, intervalMs);
    }
  };

  const pause = () => {
    paused = true;
  };

  const resume = () => {
    paused = false;
  };

  const stop = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  return { start, pause, resume, stop };
}
