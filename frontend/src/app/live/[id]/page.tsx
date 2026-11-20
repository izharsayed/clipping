"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Check,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Flame,
  Radio,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Tv,
  Volume2,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCopyText } from "@/lib/copy-text";

type ChannelDetails = {
  id: string;
  platform: "twitch" | "kick" | "youtube";
  channel_identifier: string;
  display_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  status: "live" | "offline" | "error";
  last_checked_at: string | null;
  last_live_at: string | null;
  last_error: string | null;
  max_clips_per_stream: number;
  min_clip_duration: number;
  max_clip_duration: number;
  preferred_categories: string[];
  auto_publish: boolean;
  active_session?: {
    id: string;
    title?: string | null;
    game_name?: string | null;
    started_at?: string | null;
    stream_url?: string | null;
  } | null;
  sessions?: Array<{
    id: string;
    title?: string | null;
    game_name?: string | null;
    status: string;
    started_at?: string | null;
    ended_at?: string | null;
    clips_count: number;
  }>;
};

type MomentClip = {
  id: string;
  session_id: string;
  task_id?: string | null;
  clip_id?: string | null;
  category: string;
  confidence_score: number;
  audio_energy_score: number;
  description: string;
  transcript: string;
  reason?: string | null;
  status: "pending" | "approved" | "rejected";
  created_at?: string | null;
  clip?: {
    id?: string;
    filename: string;
    duration: number;
    virality_score: number;
    hook_title?: string;
    post_text?: {
      hook?: string;
      title?: string;
      description?: string;
      hashtags?: string[];
      sparks?: string[];
    } | null;
  } | null;
};

const CATEGORY_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  highlight: { label: "Highlight", icon: "⭐", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  funny: { label: "Funny Moment", icon: "😂", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
  rage: { label: "Rage / Reaction", icon: "🔥", color: "bg-red-500/10 text-red-500 border-red-500/20" },
  clutch: { label: "Clutch Play", icon: "🎯", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
  chat_reaction: { label: "Chat Peak", icon: "💬", color: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
};

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

export default function StreamerPreviewPage() {
  const routeParams = useParams<{ id: string }>();
  const channelId = routeParams?.id || "";
  const copyText = useCopyText();

  const [channel, setChannel] = useState<ChannelDetails | null>(null);
  const [moments, setMoments] = useState<MomentClip[]>([]);
  const [loading, setLoading] = useState(true);
  const [checkingLive, setCheckingLive] = useState(false);
  const [clippingNow, setClippingNow] = useState(false);
  const [selectedDuration, setSelectedDuration] = useState<number>(45);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [hostname, setHostname] = useState<string>("localhost");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Clipping & AI Specifications state
  const [specsModalOpen, setSpecsModalOpen] = useState(false);
  const [specMinDuration, setSpecMinDuration] = useState(20);
  const [specMaxDuration, setSpecMaxDuration] = useState(60);
  const [specAutoPublish, setSpecAutoPublish] = useState(false);
  const [specMaxClips, setSpecMaxClips] = useState(10);
  const [specReframing, setSpecReframing] = useState("9:16 Vertical");
  const [specMetadataStyle, setSpecMetadataStyle] = useState("PeakCut AI");
  const [savingSpecs, setSavingSpecs] = useState(false);

  const currentReframing = useMemo(() => {
    const match = channel?.preferred_categories?.find((c) => c.startsWith("reframe:"));
    return match ? match.replace("reframe:", "") : "9:16 Vertical";
  }, [channel?.preferred_categories]);

  const currentMetadataStyle = useMemo(() => {
    const match = channel?.preferred_categories?.find((c) => c.startsWith("meta:"));
    return match ? match.replace("meta:", "") : "PeakCut AI";
  }, [channel?.preferred_categories]);

  const openSpecsModal = useCallback(() => {
    if (!channel) return;
    setSpecMinDuration(channel.min_clip_duration || 20);
    setSpecMaxDuration(channel.max_clip_duration || 60);
    setSpecAutoPublish(Boolean(channel.auto_publish));
    setSpecMaxClips(channel.max_clips_per_stream || 10);
    setSpecReframing(currentReframing);
    setSpecMetadataStyle(currentMetadataStyle);
    setSpecsModalOpen(true);
  }, [channel, currentReframing, currentMetadataStyle]);

  const applyPreset = (min: number, max: number) => {
    setSpecMinDuration(min);
    setSpecMaxDuration(max);
  };

  const handleToggleAutoPublish = async (forcedValue?: boolean) => {
    if (!channel) return;
    const nextValue = forcedValue !== undefined ? forcedValue : !channel.auto_publish;
    if (nextValue === channel.auto_publish) return;

    // Optimistically update
    setChannel((prev) => (prev ? { ...prev, auto_publish: nextValue } : prev));

    try {
      const res = await fetch(`/api/live/channels/${channelId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_publish: nextValue }),
      });

      if (res.ok) {
        const updated = await res.json();
        setChannel((prev) => (prev ? { ...prev, ...updated } : prev));
        toast.success(
          nextValue
            ? "Auto-publish enabled for approved moments"
            : "Auto-publish disabled (Manual Review)"
        );
      } else {
        setChannel((prev) => (prev ? { ...prev, auto_publish: !nextValue } : prev));
        toast.error("Failed to update auto-publish");
      }
    } catch {
      setChannel((prev) => (prev ? { ...prev, auto_publish: !nextValue } : prev));
      toast.error("Network error updating auto-publish");
    }
  };

  const handleSaveSpecs = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!channel) return;
    if (specMinDuration > specMaxDuration) {
      toast.error("Min clip duration cannot exceed max duration");
      return;
    }
    setSavingSpecs(true);

    const existingCategories = (channel.preferred_categories || []).filter(
      (c) => !c.startsWith("reframe:") && !c.startsWith("meta:")
    );
    const updatedCategories = [
      ...existingCategories,
      `reframe:${specReframing}`,
      `meta:${specMetadataStyle}`,
    ];

    try {
      const res = await fetch(`/api/live/channels/${channelId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_clip_duration: specMinDuration,
          max_clip_duration: specMaxDuration,
          auto_publish: specAutoPublish,
          max_clips_per_stream: specMaxClips,
          preferred_categories: updatedCategories,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setChannel((prev) => (prev ? { ...prev, ...data } : prev));
        toast.success("Clipping specifications updated successfully!");
        setSpecsModalOpen(false);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to update specifications");
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Error saving specifications");
    } finally {
      setSavingSpecs(false);
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      setHostname(window.location.hostname || "localhost");
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [chRes, momentsRes] = await Promise.all([
        fetch(`/api/live/channels/${channelId}`),
        fetch(`/api/live/moments?channel_id=${channelId}&limit=30`),
      ]);

      if (chRes.ok) {
        const chData = await chRes.json();
        setChannel(chData);
      }
      if (momentsRes.ok) {
        const mData = await momentsRes.json();
        setMoments(mData);
      }
    } catch (err) {
      console.error("Failed to load channel preview data:", err);
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    loadData();
    // Poll updates every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleCheckStatus = async () => {
    setCheckingLive(true);
    try {
      const res = await fetch(`/api/live/channels/${channelId}/check`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success("Stream status refreshed");
        await loadData();
      } else {
        toast.error("Failed to check stream status");
      }
    } catch {
      toast.error("Error checking stream status");
    } finally {
      setCheckingLive(false);
    }
  };

  const handleClipNow = async (customDuration?: number) => {
    setClippingNow(true);
    const dur = customDuration || selectedDuration;
    try {
      const res = await fetch(`/api/live/channels/${channelId}/clip-now`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration: dur }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(data.message || `Instant ${dur}s clip captured! Processing in background.`);
        await loadData();
      } else {
        toast.error(data.message || "Could not trigger instant clip");
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Error triggering clip");
    } finally {
      setClippingNow(false);
    }
  };

  const handleApprove = async (momentId: string) => {
    try {
      const res = await fetch(`/api/live/moments/${momentId}/approve`, { method: "POST" });
      if (res.ok) {
        toast.success("Clip approved for publishing!");
        setMoments((prev) =>
          prev.map((m) => (m.id === momentId ? { ...m, status: "approved" } : m))
        );
      }
    } catch {
      toast.error("Failed to approve moment");
    }
  };

  const handleReject = async (momentId: string) => {
    try {
      const res = await fetch(`/api/live/moments/${momentId}/reject`, { method: "POST" });
      if (res.ok) {
        toast.message("Clip rejected");
        setMoments((prev) =>
          prev.map((m) => (m.id === momentId ? { ...m, status: "rejected" } : m))
        );
      }
    } catch {
      toast.error("Failed to reject moment");
    }
  };

  const handleDeleteMoment = async (momentId: string) => {
    try {
      const res = await fetch(`/api/live/moments/${momentId}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Moment removed");
        setMoments((prev) => prev.filter((m) => m.id !== momentId));
      } else {
        toast.error("Failed to delete moment");
      }
    } catch {
      toast.error("Error deleting moment");
    }
  };

  const isActivelyRendering = (m: MomentClip) => {
    if (m.clip_id || m.clip?.id) return false;
    if (m.status === "rejected") return false;
    if (!m.created_at) return false;
    const createdTime = new Date(m.created_at).getTime();
    return Date.now() - createdTime < 180000;
  };

  const handleCopyPostText = async (moment: MomentClip) => {
    const pt = moment.clip?.post_text;
    if (!pt) {
      toast.error("No Post Text generated yet");
      return;
    }
    const fullText = [
      pt.hook ? `🔥 ${pt.hook}` : "",
      pt.title ? `\n\n${pt.title}` : "",
      pt.description ? `\n\n${pt.description}` : "",
      pt.hashtags?.length ? `\n\n${pt.hashtags.join(" ")}` : "",
    ]
      .filter(Boolean)
      .join("");

    await copyText(fullText);
    setCopiedId(moment.id);
    toast.success("PeakCut Post Text copied to clipboard!");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const embedUrl = useMemo(() => {
    if (!channel) return null;
    const { platform, channel_identifier } = channel;

    if (platform === "twitch") {
      return `https://player.twitch.tv/?channel=${encodeURIComponent(
        channel_identifier
      )}&parent=${hostname}&autoplay=true&muted=false`;
    }
    if (platform === "kick") {
      return `https://player.kick.com/${encodeURIComponent(
        channel_identifier
      )}?autoplay=true&muted=false`;
    }
    if (platform === "youtube") {
      if (channel_identifier.startsWith("@") || channel_identifier.length > 20) {
        return `https://www.youtube-nocookie.com/embed/live_stream?channel=${encodeURIComponent(
          channel_identifier
        )}&autoplay=1`;
      }
      return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(
        channel_identifier
      )}?autoplay=1&live=1`;
    }
    return null;
  }, [channel, hostname]);

  const externalPlatformUrl = useMemo(() => {
    if (!channel) return "#";
    const { platform, channel_identifier } = channel;
    if (platform === "twitch") return `https://twitch.tv/${channel_identifier}`;
    if (platform === "kick") return `https://kick.com/${channel_identifier}`;
    if (platform === "youtube") {
      return channel_identifier.startsWith("@")
        ? `https://youtube.com/${channel_identifier}/live`
        : `https://youtube.com/watch?v=${channel_identifier}`;
    }
    return "#";
  }, [channel]);

  const filteredMoments = useMemo(() => {
    if (filterStatus === "all") return moments;
    return moments.filter((m) => m.status === filterStatus);
  }, [moments, filterStatus]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-6 space-y-6 max-w-7xl mx-auto">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <Skeleton className="lg:col-span-8 h-[520px] rounded-2xl" />
          <Skeleton className="lg:col-span-4 h-[520px] rounded-2xl" />
        </div>
      </div>
    );
  }

  if (!channel) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6 text-center">
        <AlertCircle className="size-12 text-destructive mb-3" />
        <h2 className="text-xl font-bold">Streamer Not Found</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-sm">
          This channel might have been removed or does not belong to your account.
        </p>
        <Button asChild className="mt-4 gap-2">
          <Link href="/live">
            <ArrowLeft className="size-4" /> Back to Live Engine
          </Link>
        </Button>
      </div>
    );
  }

  const isLive = channel.status === "live";

  return (
    <div className="min-h-screen bg-background text-foreground pb-16">
      {/* Top Header Bar */}
      <header className="border-b bg-card/60 backdrop-blur sticky top-0 z-30 px-4 sm:px-8 py-3.5">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Button asChild variant="ghost" size="icon" className="shrink-0 size-9">
              <Link href="/live" title="Back to Live Engine">
                <ArrowLeft className="size-4" />
              </Link>
            </Button>

            <div className="flex items-center gap-3 min-w-0">
              {channel.avatar_url ? (
                <Image
                  src={channel.avatar_url}
                  alt={channel.display_name}
                  width={42}
                  height={42}
                  className="rounded-full border border-border shrink-0 shadow-sm"
                  unoptimized
                />
              ) : (
                <div className="size-10 rounded-full bg-primary/20 text-primary font-bold flex items-center justify-center shrink-0">
                  {channel.display_name.slice(0, 2).toUpperCase()}
                </div>
              )}

              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-base sm:text-lg font-bold tracking-tight truncate">
                    {channel.display_name}
                  </h1>
                  <Badge variant="outline" className="text-[10px] uppercase font-mono px-1.5 py-0">
                    {channel.platform}
                  </Badge>
                  {isLive ? (
                    <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[11px] gap-1.5 px-2 py-0.5 animate-pulse">
                      <span className="size-1.5 rounded-full bg-emerald-400" />
                      LIVE NOW
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-[11px] text-muted-foreground uppercase">
                      OFFLINE
                    </Badge>
                  )}
                </div>

                <p className="text-xs text-muted-foreground truncate max-w-md">
                  {channel.active_session?.title ||
                    (isLive ? "Live Stream Broadcast" : "Currently offline")}
                  {channel.active_session?.game_name && (
                    <span className="text-foreground/80 font-medium">
                      {" "}
                      · {channel.active_session.game_name}
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* Action Bar */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCheckStatus}
              disabled={checkingLive}
              className="gap-1.5 text-xs h-8"
            >
              <RefreshCw className={`size-3.5 ${checkingLive ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Check Live</span>
            </Button>

            <Button asChild variant="outline" size="sm" className="gap-1.5 text-xs h-8">
              <a href={externalPlatformUrl} target="_blank" rel="noreferrer">
                <span>Watch on {channel.platform}</span>
                <ExternalLink className="size-3 opacity-60" />
              </a>
            </Button>

            {/* Instant Manual Clip Duration Selector & Trigger */}
            <div className="flex items-center gap-1 bg-muted/60 p-0.5 rounded-lg border border-border/50">
              {[20, 30, 45, 60].map((sec) => (
                <button
                  key={sec}
                  type="button"
                  onClick={() => setSelectedDuration(sec)}
                  className={`px-2 py-1 text-[11px] font-semibold rounded-md transition-all ${
                    selectedDuration === sec
                      ? "bg-amber-500 text-white shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  title={`Set manual clip length to ${sec}s`}
                >
                  {sec}s
                </button>
              ))}
            </div>

            <Button
              size="sm"
              onClick={() => handleClipNow()}
              disabled={clippingNow}
              className="gap-2 text-xs font-semibold h-8 bg-gradient-to-r from-amber-500 to-primary hover:from-amber-600 hover:to-primary/90 text-white shadow-sm"
              title={`Clip past ${selectedDuration} seconds from live stream`}
            >
              <Zap className={`size-3.5 ${clippingNow ? "animate-spin" : ""}`} />
              <span>{clippingNow ? "Clipping..." : `⚡ Clip This Now (${selectedDuration}s)`}</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Main Studio Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-8 pt-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT COLUMN: LIVE VIDEO PLAYER & TELEMETRY (8 cols) */}
          <div className="lg:col-span-8 space-y-6">
            {/* Live Video Player Frame */}
            <Card className="border bg-card overflow-hidden shadow-sm">
              <div className="relative aspect-video w-full bg-black flex items-center justify-center overflow-hidden">
                {isLive && embedUrl ? (
                  <iframe
                    src={embedUrl}
                    title={`${channel.display_name} live player`}
                    className="w-full h-full border-0"
                    allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
                    allowFullScreen
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center p-8 text-center max-w-md space-y-3">
                    <div className="size-16 rounded-2xl bg-muted/60 border border-border flex items-center justify-center text-muted-foreground/60 shadow-inner">
                      <Tv className="size-8" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-foreground">
                        {channel.display_name} is Offline
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        The live embedded player activates automatically as soon as the streamer starts
                        broadcasting on {channel.platform.toUpperCase()}.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 pt-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleCheckStatus}
                        disabled={checkingLive}
                        className="gap-1.5 text-xs"
                      >
                        <RefreshCw className={`size-3.5 ${checkingLive ? "animate-spin" : ""}`} />
                        Refresh Live Status
                      </Button>
                      <Button asChild size="sm" variant="ghost" className="text-xs">
                        <a href={externalPlatformUrl} target="_blank" rel="noreferrer">
                          Open Profile <ExternalLink className="size-3 ml-1" />
                        </a>
                      </Button>
                    </div>
                  </div>
                )}

                {/* Live Floating Badge */}
                {isLive && (
                  <div className="absolute top-3 left-3 pointer-events-none flex items-center gap-2">
                    <Badge className="bg-black/75 backdrop-blur-md text-emerald-400 border border-emerald-500/30 text-[10px] font-mono gap-1.5 px-2 py-0.5">
                      <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      LIVE FEED
                    </Badge>
                  </div>
                )}
              </div>

              {/* Stream Title & Game Bar */}
              <div className="p-4 flex flex-wrap items-center justify-between gap-3 border-t bg-card">
                <div className="min-w-0">
                  <h2 className="text-sm font-bold tracking-tight truncate">
                    {channel.active_session?.title || `${channel.display_name} Stream Studio`}
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Category:{" "}
                    <span className="font-medium text-foreground">
                      {channel.active_session?.game_name || "General"}
                    </span>
                    {channel.last_live_at && (
                      <span> · Last Live: {new Date(channel.last_live_at).toLocaleDateString()}</span>
                    )}
                  </p>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Rolling Buffer:</span>
                  <Badge variant="outline" className="font-mono text-[11px] text-primary border-primary/20 bg-primary/5">
                    {channel.max_clip_duration + 30}s FIFO
                  </Badge>
                </div>
              </div>
            </Card>

            {/* Audio Telemetry & Live Clip Engine Specs */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Simulated Audio Energy Visualizer */}
              <Card className="border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                    <Volume2 className="size-3.5 text-primary" />
                    Speech & Energy Radar
                  </span>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {isLive ? "Active Listening" : "Standby"}
                  </Badge>
                </div>

                {/* Animated Waveform Bars */}
                <div className="h-14 flex items-end gap-1.5 px-2 py-1 bg-muted/40 rounded-xl border border-border/50 overflow-hidden">
                  {[24, 45, 78, 62, 89, 95, 70, 48, 82, 91, 65, 38, 55, 75, 88, 60, 42, 68, 85, 52].map(
                    (val, idx) => (
                      <div
                        key={idx}
                        style={{
                          height: isLive ? `${val}%` : "12%",
                        }}
                        className={`flex-1 rounded-full transition-all duration-300 ${
                          isLive
                            ? val > 75
                              ? "bg-amber-500 animate-pulse"
                              : "bg-primary"
                            : "bg-muted-foreground/30"
                        }`}
                      />
                    )
                  )}
                </div>

                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Virality Threshold: 80%</span>
                  <span>Audio Peak: {isLive ? "High Dialogue" : "Quiet"}</span>
                </div>
              </Card>

              {/* Engine Clipping Rules */}
              <Card className="border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                    <Sparkles className="size-3.5 text-primary" />
                    Clipping & AI Specifications
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openSpecsModal()}
                    className="h-6 text-[11px] px-2 gap-1 rounded border-border/60 hover:border-primary/40 text-muted-foreground hover:text-foreground"
                  >
                    <SlidersHorizontal className="size-3" />
                    Configure
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs pt-1">
                  {/* Clip Length Tile */}
                  <button
                    type="button"
                    onClick={() => openSpecsModal()}
                    className="p-2.5 rounded-lg bg-muted/40 border border-border/40 text-left hover:border-primary/50 hover:bg-muted/60 transition cursor-pointer group flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                        Clip Length
                      </span>
                      <SlidersHorizontal className="size-3 text-muted-foreground/60 group-hover:text-primary transition" />
                    </div>
                    <div>
                      <span className="font-bold text-foreground">
                        {channel.min_clip_duration}s – {channel.max_clip_duration}s
                      </span>
                      <span className="text-[10px] text-primary block mt-0.5 font-medium">
                        AI Dynamic & Configurable
                      </span>
                    </div>
                  </button>

                  {/* Auto-Publish Tile with Inline Switch */}
                  <div
                    onClick={() => handleToggleAutoPublish(!channel.auto_publish)}
                    className="p-2.5 rounded-lg bg-muted/40 border border-border/40 flex flex-col justify-between hover:border-primary/50 hover:bg-muted/60 transition cursor-pointer select-none"
                    role="button"
                    tabIndex={0}
                    aria-label="Toggle Auto-Publish"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleToggleAutoPublish(!channel.auto_publish);
                      }
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                        Auto-Publish
                      </span>
                      <div onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={channel.auto_publish}
                          onCheckedChange={(val) => handleToggleAutoPublish(val)}
                          className="scale-75 origin-right"
                          aria-label="Auto-publish switch"
                        />
                      </div>
                    </div>
                    <div>
                      <span className="font-bold text-foreground">
                        {channel.auto_publish ? "Enabled" : "Manual Review"}
                      </span>
                      <span className="text-[10px] text-muted-foreground block mt-0.5 font-medium">
                        {channel.auto_publish ? "Direct to socials" : "Click to enable"}
                      </span>
                    </div>
                  </div>

                  {/* Reframing Tile */}
                  <button
                    type="button"
                    onClick={() => openSpecsModal()}
                    className="p-2.5 rounded-lg bg-muted/40 border border-border/40 text-left hover:border-primary/50 hover:bg-muted/60 transition cursor-pointer group flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                        Reframing
                      </span>
                      <SlidersHorizontal className="size-3 text-muted-foreground/60 group-hover:text-primary transition" />
                    </div>
                    <div>
                      <span className="font-bold text-foreground">{currentReframing}</span>
                      <span className="text-[10px] text-muted-foreground block mt-0.5 font-medium">
                        AI Focus & Framing
                      </span>
                    </div>
                  </button>

                  {/* Post Metadata Tile */}
                  <button
                    type="button"
                    onClick={() => openSpecsModal()}
                    className="p-2.5 rounded-lg bg-muted/40 border border-border/40 text-left hover:border-primary/50 hover:bg-muted/60 transition cursor-pointer group flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                        Post Metadata
                      </span>
                      <SlidersHorizontal className="size-3 text-muted-foreground/60 group-hover:text-primary transition" />
                    </div>
                    <div>
                      <span className="font-bold text-foreground">{currentMetadataStyle}</span>
                      <span className="text-[10px] text-muted-foreground block mt-0.5 font-medium">
                        Viral Hooks & Captions
                      </span>
                    </div>
                  </button>
                </div>

                <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                  <span>Stream Quota: <strong className="text-foreground font-semibold">{channel.max_clips_per_stream || 10} clips</strong> / stream</span>
                  <button
                    type="button"
                    onClick={() => openSpecsModal()}
                    className="text-primary hover:underline font-medium cursor-pointer"
                  >
                    Configure rules →
                  </button>
                </div>
              </Card>
            </div>
          </div>

          {/* RIGHT COLUMN: DETECTED MOMENTS & CLIPS FEED (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <Card className="border bg-card">
              <CardHeader className="p-4 pb-3 border-b">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Sparkles className="size-4 text-primary" />
                    Channel Clips & Moments
                  </CardTitle>
                  <Badge variant="outline" className="font-mono text-xs">
                    {moments.length}
                  </Badge>
                </div>
                <CardDescription className="text-xs mt-0.5">
                  Real-time moments detected from {channel.display_name}&apos;s stream
                </CardDescription>

                {/* Filter Pills */}
                <div className="flex gap-1.5 pt-2">
                  {[
                    { id: "all", label: "All" },
                    { id: "pending", label: "Pending" },
                    { id: "approved", label: "Approved" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setFilterStatus(tab.id)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all ${
                        filterStatus === tab.id
                          ? "bg-primary text-primary-foreground shadow-xs"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </CardHeader>

              <CardContent className="p-4 space-y-4 max-h-[720px] overflow-y-auto">
                {filteredMoments.length === 0 ? (
                  <div className="py-12 text-center text-muted-foreground space-y-2">
                    <Radio className="size-8 mx-auto opacity-40" />
                    <p className="text-xs font-semibold text-foreground">No moments in this list</p>
                    <p className="text-[11px] max-w-xs mx-auto">
                      Click the &ldquo;⚡ Clip This Now&rdquo; button above to capture an instant clip from
                      the stream buffer.
                    </p>
                  </div>
                ) : (
                  filteredMoments.map((moment) => {
                    const cat = CATEGORY_LABELS[moment.category] || CATEGORY_LABELS.highlight;
                    const pt = moment.clip?.post_text;

                    return (
                      <div
                        key={moment.id}
                        className="rounded-xl border bg-card/60 p-3.5 space-y-3 hover:border-primary/40 transition-colors"
                      >
                        {/* Top Meta */}
                        <div className="flex items-center justify-between gap-2">
                          <Badge variant="outline" className={`text-[10px] font-semibold gap-1 ${cat.color}`}>
                            <span>{cat.icon}</span>
                            <span>{cat.label}</span>
                          </Badge>

                          {moment.clip?.virality_score ? (
                            <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[10px] font-mono">
                              <Flame className="size-3 mr-0.5 fill-emerald-400" />
                              {moment.clip.virality_score} Virality
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-[10px] uppercase font-mono">
                              {moment.status}
                            </Badge>
                          )}
                        </div>

                        {/* Video Player or Processing Placeholder */}
                        {moment.task_id && (moment.clip_id || moment.clip?.id) ? (
                          <div className="relative aspect-[9/16] max-h-[220px] w-full rounded-lg bg-black overflow-hidden border border-border">
                            <video
                              controls
                              className="w-full h-full object-contain"
                              src={`/api/tasks/${moment.task_id}/clips/${moment.clip_id || moment.clip?.id}/file`}
                            />
                            {moment.clip?.duration ? (
                              <div className="absolute bottom-2 right-2 pointer-events-none">
                                <Badge className="bg-black/75 backdrop-blur-sm text-white text-[10px] font-mono px-1.5 py-0 border border-white/10">
                                  <Clock className="size-2.5 mr-1 opacity-70" />
                                  {formatDuration(moment.clip.duration)}
                                </Badge>
                              </div>
                            ) : null}
                          </div>
                        ) : isActivelyRendering(moment) ? (
                          <div className="p-3 bg-muted/40 rounded-lg border border-border/50 text-center space-y-1">
                            <RefreshCw className="size-5 mx-auto text-primary animate-spin" />
                            <p className="text-[11px] font-semibold text-foreground">
                              Processing 9:16 Video...
                            </p>
                            <p className="text-[10px] text-muted-foreground">
                              Transcribing speech & active speaker framing
                            </p>
                          </div>
                        ) : (
                          <div className="p-3 bg-muted/40 rounded-lg border border-border/50 text-center space-y-1.5">
                            <AlertTriangle className="size-5 mx-auto text-amber-500/80" />
                            <p className="text-[11px] font-semibold text-foreground">
                              Clip Unavailable
                            </p>
                            <p className="text-[10px] text-muted-foreground">
                              Buffer expired or render incomplete
                            </p>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-[10px] h-6 text-destructive hover:bg-destructive/10"
                              onClick={() => handleDeleteMoment(moment.id)}
                            >
                              <Trash2 className="size-2.5 mr-1" /> Remove
                            </Button>
                          </div>
                        )}

                        {/* Title & Post Text Hook */}
                        <div className="space-y-1">
                          <h4 className="text-xs font-bold line-clamp-2 text-foreground">
                            {pt?.title || moment.clip?.hook_title || moment.description}
                          </h4>
                          {pt?.hook && (
                            <p className="text-[11px] font-mono font-semibold text-primary uppercase">
                              Hook: &ldquo;{pt.hook}&rdquo;
                            </p>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60">
                          <div className="flex items-center gap-1.5">
                            {moment.status === "pending" && (
                              <>
                                <Button
                                  size="sm"
                                  onClick={() => handleApprove(moment.id)}
                                  className="h-7 text-[11px] px-2.5 gap-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                                >
                                  <Check className="size-3" /> Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleReject(moment.id)}
                                  className="h-7 text-[11px] px-2 text-muted-foreground hover:text-destructive"
                                >
                                  <X className="size-3" />
                                </Button>
                              </>
                            )}
                            {moment.status === "approved" && (
                              <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">
                                Approved
                              </Badge>
                            )}
                          </div>

                          <div className="flex items-center gap-1">
                            {pt && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleCopyPostText(moment)}
                                className="h-7 text-[10px] px-2 gap-1"
                                title="Copy Post Text"
                              >
                                {copiedId === moment.id ? (
                                  <Check className="size-3 text-emerald-400" />
                                ) : (
                                  <Copy className="size-3" />
                                )}
                                <span>Copy</span>
                              </Button>
                            )}

                            {moment.task_id && (moment.clip_id || moment.clip?.id) && (
                              <Button asChild size="sm" variant="ghost" className="h-7 size-7 p-0">
                                <a
                                  href={`/api/tasks/${moment.task_id}/clips/${moment.clip_id || moment.clip?.id}/file`}
                                  download
                                  title="Download clip"
                                >
                                  <Download className="size-3.5" />
                                </a>
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 size-7 p-0 text-muted-foreground hover:text-destructive"
                              onClick={() => handleDeleteMoment(moment.id)}
                              title="Remove moment"
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Clipping & AI Specifications Configuration Dialog */}
        <Dialog open={specsModalOpen} onOpenChange={setSpecsModalOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Sparkles className="size-4 text-primary" />
                Clipping & AI Specifications
              </DialogTitle>
              <DialogDescription>
                Tune live hype detection thresholds, clip durations, reframing style, and publishing rules for {channel.display_name}.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSaveSpecs} className="space-y-4 pt-2">
              {/* Quick Presets */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Quick Duration Presets</Label>
                <div className="grid grid-cols-3 gap-2">
                  <Button
                    type="button"
                    variant={specMinDuration === 15 && specMaxDuration === 30 ? "default" : "outline"}
                    size="sm"
                    className="text-xs h-7"
                    onClick={() => applyPreset(15, 30)}
                  >
                    Shorts (15–30s)
                  </Button>
                  <Button
                    type="button"
                    variant={specMinDuration === 20 && specMaxDuration === 60 ? "default" : "outline"}
                    size="sm"
                    className="text-xs h-7"
                    onClick={() => applyPreset(20, 60)}
                  >
                    Balanced (20–60s)
                  </Button>
                  <Button
                    type="button"
                    variant={specMinDuration === 30 && specMaxDuration === 90 ? "default" : "outline"}
                    size="sm"
                    className="text-xs h-7"
                    onClick={() => applyPreset(30, 90)}
                  >
                    Longform (30–90s)
                  </Button>
                </div>
              </div>

              {/* Min and Max Duration Sliders */}
              <div className="grid grid-cols-2 gap-4 p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Min Duration</Label>
                    <span className="text-xs font-semibold text-primary">{specMinDuration}s</span>
                  </div>
                  <Slider
                    aria-label="Min clip duration"
                    value={[specMinDuration]}
                    min={10}
                    max={45}
                    step={5}
                    onValueChange={([val]) => {
                      setSpecMinDuration(val);
                      if (val > specMaxDuration) setSpecMaxDuration(val);
                    }}
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Max Duration</Label>
                    <span className="text-xs font-semibold text-primary">{specMaxDuration}s</span>
                  </div>
                  <Slider
                    aria-label="Max clip duration"
                    value={[specMaxDuration]}
                    min={20}
                    max={90}
                    step={5}
                    onValueChange={([val]) => {
                      setSpecMaxDuration(val);
                      if (val < specMinDuration) setSpecMinDuration(val);
                    }}
                  />
                </div>
              </div>

              {/* Max Clips Per Stream */}
              <div className="space-y-1.5 p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Max Clips Per Stream</Label>
                  <span className="text-xs font-semibold text-primary">{specMaxClips} clips</span>
                </div>
                <Slider
                  aria-label="Max clips per stream"
                  value={[specMaxClips]}
                  min={1}
                  max={30}
                  step={1}
                  onValueChange={([val]) => setSpecMaxClips(val)}
                />
                <span className="text-[11px] text-muted-foreground block">
                  Limits how many highlight clips the AI engine will cut per broadcast session.
                </span>
              </div>

              {/* Reframing Style */}
              <div className="space-y-1.5">
                <Label className="text-xs">Reframing Layout</Label>
                <Select value={specReframing} onValueChange={setSpecReframing}>
                  <SelectTrigger className="w-full text-xs">
                    <SelectValue placeholder="Select layout" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="9:16 Vertical">9:16 Vertical (Single Subject / Face-Tracked)</SelectItem>
                    <SelectItem value="9:16 Split Screen">9:16 Split Screen (Facecam Top + Gameplay Center)</SelectItem>
                    <SelectItem value="16:9 Landscape">16:9 Landscape (Original Wide Highlight)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Post Metadata Style */}
              <div className="space-y-1.5">
                <Label className="text-xs">Post Metadata & Copy Generation</Label>
                <Select value={specMetadataStyle} onValueChange={setSpecMetadataStyle}>
                  <SelectTrigger className="w-full text-xs">
                    <SelectValue placeholder="Select style" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PeakCut AI">PeakCut AI (Balanced High-Virality Hook & Hashtags)</SelectItem>
                    <SelectItem value="Viral Hooks">Viral Hooks (Curiosity-Gap Punchy 1-Liners)</SelectItem>
                    <SelectItem value="Story Arc">Story Arc (Detailed Narrative & Context)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Auto-Publish Switch */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/40 border border-border/40">
                <div className="space-y-0.5">
                  <Label className="text-xs font-medium">Auto-Publish to Channels</Label>
                  <p className="text-[11px] text-muted-foreground">
                    Skip manual review and automatically publish newly rendered viral moments.
                  </p>
                </div>
                <Switch
                  checked={specAutoPublish}
                  onCheckedChange={setSpecAutoPublish}
                  aria-label="Auto-publish switch in modal"
                />
              </div>

              <DialogFooter className="pt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSpecsModalOpen(false)}
                  disabled={savingSpecs}
                >
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={savingSpecs}>
                  {savingSpecs ? "Saving..." : "Save Specifications"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}