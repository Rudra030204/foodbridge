import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Countdown } from "../components/ui";
import { formatDuration, urgencyOf, utcMs } from "../lib/format";
import { useCountdown } from "./useCountdown";

const NOW = new Date("2026-06-01T06:30:00Z");

describe("countdown", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW); });
  afterEach(() => vi.useRealTimers());

  it("treats the API's naive timestamps as UTC", () => {
    expect(utcMs("2026-06-01T07:30:00")).toBe(new Date("2026-06-01T07:30:00Z").getTime());
    expect(utcMs("2026-06-01T07:30:00+05:30")).toBe(new Date("2026-06-01T02:00:00Z").getTime());
    expect(Number.isNaN(utcMs(null))).toBe(true);
  });

  it("formats durations", () => {
    expect(formatDuration(65_000)).toBe("1m 05s");
    expect(formatDuration(3_725_000)).toBe("1h 02m 05s");
    expect(formatDuration(-5000)).toBe("0m 00s");
  });

  it("maps minutes left to green / amber / red", () => {
    expect(urgencyOf(30 * 60000)).toBe("red");
    expect(urgencyOf(90 * 60000)).toBe("amber");
    expect(urgencyOf(180 * 60000)).toBe("green");
  });

  it("counts down every second and stops at zero", () => {
    const { result } = renderHook(() => useCountdown("2026-06-01T06:30:03"));
    expect(result.current.ms).toBe(3000);
    act(() => { vi.advanceTimersByTime(2000); });
    expect(result.current.ms).toBe(1000);
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current.ms).toBe(0);
    expect(result.current.expired).toBe(true);
  });

  it("renders the right urgency colour and the expired state", () => {
    const { rerender } = render(<Countdown safeUntil="2026-06-01T07:00:00" />); // 30 min left
    expect(screen.getByTestId("countdown")).toHaveAttribute("data-urgency", "red");
    rerender(<Countdown safeUntil="2026-06-01T08:00:00" />); // 90 min
    expect(screen.getByTestId("countdown")).toHaveAttribute("data-urgency", "amber");
    rerender(<Countdown safeUntil="2026-06-01T10:00:00" />); // 210 min
    expect(screen.getByTestId("countdown")).toHaveAttribute("data-urgency", "green");
    rerender(<Countdown safeUntil="2026-06-01T06:00:00" />);
    expect(screen.getByTestId("countdown")).toHaveTextContent("Expired");
  });
});
