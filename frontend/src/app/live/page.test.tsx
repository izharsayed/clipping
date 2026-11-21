import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import LiveDashboardPage from "./page";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), message: vi.fn(), error: vi.fn() },
}));

const mockChannels = [
  {
    id: "ch-active",
    platform: "twitch",
    channel_identifier: "hutchmf",
    display_name: "HutchMF",
    avatar_url: null,
    is_active: true,
    status: "offline",
    last_checked_at: "2026-11-21T06:00:00Z",
    last_live_at: null,
    last_error: null,
    max_clips_per_stream: 5,
    min_clip_duration: 20,
    max_clip_duration: 60,
    clips_count: 1,
    active_session: null,
  },
  {
    id: "ch-paused",
    platform: "twitch",
    channel_identifier: "asianjeff",
    display_name: "AsianJeff",
    avatar_url: null,
    is_active: false,
    status: "live",
    last_checked_at: "2026-11-21T06:00:00Z",
    last_live_at: "2026-11-21T06:00:00Z",
    last_error: null,
    max_clips_per_stream: 5,
    min_clip_duration: 20,
    max_clip_duration: 60,
    clips_count: 4,
    active_session: {
      id: "sess-1",
      title: "AsianJeff (live) 2026-11-21",
      game_name: "Fortnite",
      started_at: "2026-11-21T04:42:00Z",
      stream_url: "https://twitch.tv/asianjeff",
    },
  },
];

const mockStats = {
  monitored_channels_count: 1,
  currently_live_count: 0,
  streams_processed_count: 2,
  total_clips_count: 5,
  clips_awaiting_approval: 0,
  processing_errors_count: 0,
};

describe("LiveDashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/live/overview")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockStats),
        });
      }
      if (url.includes("/api/live/moments")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        });
      }
      if (url.includes("/api/live/channels/ch-paused") && init?.method === "PATCH") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: "ch-paused", is_active: true }),
        });
      }
      if (url.includes("/api/live/channels/ch-active") && init?.method === "PATCH") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: "ch-active", is_active: false }),
        });
      }
      if (url.includes("/api/live/channels")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockChannels),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });
  });

  it("renders live dashboard and displays channels tab with active and paused status", async () => {
    render(<LiveDashboardPage />);

    // Wait for channels data to load
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Live Channels \(2\)/i })).toBeInTheDocument();
    });

    // Switch to channels tab
    const channelsTab = screen.getByRole("tab", { name: /Live Channels \(2\)/i });
    fireEvent.click(channelsTab);

    // Verify channel names rendered
    expect(await screen.findByText(/HutchMF/i)).toBeInTheDocument();
    expect(await screen.findByText(/AsianJeff/i)).toBeInTheDocument();

    // Verify AsianJeff displays PAUSED badge because is_active is false
    expect(screen.getByText("PAUSED")).toBeInTheDocument();

    // Verify switch labels
    const activeLabels = screen.getAllByText("Active");
    expect(activeLabels.length).toBeGreaterThan(0);
    const pausedLabels = screen.getAllByText("Paused");
    expect(pausedLabels.length).toBeGreaterThan(0);
  });

  it("optimistically toggles channel active state when pause switch is clicked", async () => {
    render(<LiveDashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Live Channels \(2\)/i })).toBeInTheDocument();
    });

    const channelsTab = screen.getByRole("tab", { name: /Live Channels \(2\)/i });
    fireEvent.click(channelsTab);

    await screen.findByText(/AsianJeff/i);

    // Click the toggle switch for paused channel
    const switches = screen.getAllByRole("switch");
    expect(switches.length).toBe(2);

    // The second switch is for AsianJeff (paused)
    fireEvent.click(switches[1]);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/live/channels/ch-paused",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ is_active: true }),
        })
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Channel monitoring active");
    });
  });
});
