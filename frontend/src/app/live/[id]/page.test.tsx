import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { toast } from "sonner";
import StreamerPreviewPage from "./page";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), message: vi.fn(), error: vi.fn() },
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "ch-123" }),
}));

const mockChannel = {
  id: "ch-123",
  platform: "twitch",
  channel_identifier: "ninja",
  display_name: "Ninja",
  avatar_url: "https://static-cdn.jtvnw.net/avatar.png",
  is_active: true,
  status: "live",
  last_checked_at: "2026-11-19T10:00:00Z",
  last_live_at: "2026-11-19T10:00:00Z",
  last_error: null,
  max_clips_per_stream: 10,
  min_clip_duration: 15,
  max_clip_duration: 60,
  preferred_categories: ["Fortnite"],
  auto_publish: false,
  active_session: {
    id: "sess-1",
    title: "Fortnite Ranked Cup Champions Finals",
    game_name: "Fortnite",
    started_at: "2026-11-19T09:30:00Z",
    stream_url: "https://twitch.tv/ninja",
  },
};

const mockMoments = [
  {
    id: "moment-1",
    session_id: "sess-1",
    task_id: "task-100",
    clip_id: "clip-200",
    category: "highlight",
    confidence_score: 0.94,
    audio_energy_score: 0.89,
    description: "Insane 1v3 Victory Royale",
    transcript: "He hits the sniper shot, clutches the 1v3!",
    reason: "Audio energy peak and crowd applause",
    status: "pending",
    created_at: "2026-11-19T09:45:00Z",
    clip: {
      filename: "live_clip_1.mp4",
      duration: 32.5,
      virality_score: 94,
      hook_title: "1v3 CLUTCH ROYALE",
      post_text: {
        hook: "HE DID NOT JUST HIT THAT",
        title: "Ninja Clutches Insane 1v3 in Finals",
        description: "Watch this incredible clutch in the tournament finals.",
        hashtags: ["#gaming", "#fortnite", "#clutch"],
        sparks: ["insane", "unreal"],
      },
    },
  },
];

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes("/api/live/channels/ch-123/clip-now")) {
        return new Response(
          JSON.stringify({
            success: true,
            status: "processing",
            message: "Instant clip captured! Processing in background.",
          }),
          { status: 200 }
        );
      }
      if (url.includes("/api/live/channels/ch-123/check")) {
        return new Response(JSON.stringify({ status: "live", is_live: true }), { status: 200 });
      }
      if (url.includes("/api/live/moments/moment-1/approve")) {
        return new Response(JSON.stringify({ id: "moment-1", status: "approved" }), { status: 200 });
      }
      if (url.includes("/api/live/channels/ch-123")) {
        if (init?.method === "PATCH") {
          const body = init?.body ? JSON.parse(init.body as string) : {};
          return new Response(JSON.stringify({ ...mockChannel, ...body }), { status: 200 });
        }
        return new Response(JSON.stringify(mockChannel), { status: 200 });
      }
      if (url.includes("/api/live/moments")) {
        return new Response(JSON.stringify(mockMoments), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    })
  );
});

it("renders the streamer preview studio with embedded player and channel details", async () => {
  render(<StreamerPreviewPage />);

  // Streamer header details
  expect(await screen.findByRole("heading", { name: "Ninja" })).toBeInTheDocument();
  expect(screen.getByText("LIVE NOW")).toBeInTheDocument();
  expect(screen.getAllByText(/Fortnite Ranked Cup Champions Finals/).length).toBeGreaterThan(0);

  // Embedded player iframe
  const iframe = screen.getByTitle("Ninja live player") as HTMLIFrameElement;
  expect(iframe).toBeInTheDocument();
  expect(iframe.src).toContain("player.twitch.tv");
  expect(iframe.src).toContain("channel=ninja");

  // Telemetry radar and rules
  expect(screen.getByText("Speech & Energy Radar")).toBeInTheDocument();
  expect(screen.getByText("15s – 60s")).toBeInTheDocument();

  // Channel moments feed
  expect(screen.getByText("Ninja Clutches Insane 1v3 in Finals")).toBeInTheDocument();
  expect(screen.getByText(/HE DID NOT JUST HIT THAT/)).toBeInTheDocument();
  expect(screen.getByText("94 Virality")).toBeInTheDocument();
});

it("triggers instant clip capture on Clip This Now button click", async () => {
  render(<StreamerPreviewPage />);

  const clipBtn = await screen.findByRole("button", { name: /Clip This Now/i });
  expect(clipBtn).toBeInTheDocument();

  fireEvent.click(clipBtn);

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/live/channels/ch-123/clip-now",
      expect.objectContaining({ method: "POST" })
    );
  });
  await waitFor(() => {
    expect(toast.success).toHaveBeenCalledWith("Instant clip captured! Processing in background.");
  });
  // Wait until clipping finishes
  await waitFor(() => {
    expect(screen.getByRole("button", { name: /Clip This Now/i })).not.toBeDisabled();
  });
});

it("approves pending moment clip", async () => {
  render(<StreamerPreviewPage />);

  const approveBtn = await screen.findByRole("button", { name: /^Approve$/i });
  fireEvent.click(approveBtn);

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/live/moments/moment-1/approve",
      expect.objectContaining({ method: "POST" })
    );
  });
  await waitFor(() => {
    expect(toast.success).toHaveBeenCalledWith("Clip approved for publishing!");
  });
});

it("toggles auto-publish setting inline from the card", async () => {
  render(<StreamerPreviewPage />);

  expect(await screen.findByText("Manual Review")).toBeInTheDocument();

  const autoPublishTile = screen.getByRole("button", { name: /Toggle Auto-Publish/i });
  fireEvent.click(autoPublishTile);

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/live/channels/ch-123",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ auto_publish: true }),
      })
    );
  });
  await waitFor(() => {
    expect(toast.success).toHaveBeenCalledWith("Auto-publish enabled for approved moments");
  });
});

it("opens specifications configuration modal and saves updated clipping rules", async () => {
  render(<StreamerPreviewPage />);

  const configBtn = await screen.findByRole("button", { name: /^Configure$/i });
  fireEvent.click(configBtn);

  expect(await screen.findByRole("heading", { name: "Clipping & AI Specifications" })).toBeInTheDocument();

  const presetBtn = screen.getByRole("button", { name: /Shorts \(15–30s\)/i });
  fireEvent.click(presetBtn);

  const saveBtn = screen.getByRole("button", { name: /Save Specifications/i });
  fireEvent.click(saveBtn);

  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/live/channels/ch-123",
      expect.objectContaining({
        method: "PATCH",
      })
    );
  });
  await waitFor(() => {
    expect(toast.success).toHaveBeenCalledWith("Clipping specifications updated successfully!");
  });
});
