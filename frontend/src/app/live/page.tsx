/* eslint-disable @next/next/no-img-element */
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Flame,
  Plus,
  Radio,
  RefreshCw,
  Sparkles,
  Trash2,
  Tv,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type MonitoredChannel = {
  id: string;
  platform: "twitch" | "kick" | "youtube";
  channel_identifier: string;
  display_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  status: "monitoring" | "live" | "offline" | "processing" | "error";
  last_checked_at?: string | null;
  last_live_at?: string | null;
  last_error?: string | null;
  max_clips_per_stream: number;
  min_clip_duration: number;
  max_clip_duration: number;
  clips_count: number;
  active_session?: {
    id: string;
    title?: string;
    game_name?: string;
    started_at: string;
    stream_url?: string;
  } | null;
};

type LiveMoment = {
  id: string;
  session_id: string;
  task_id?: string | null;
  clip_id?: string | null;
  category: string;
  confidence_score: number;
  audio_energy_score: number;
  description?: string | null;
  transcript?: string | null;
  reason?: string | null;
  status: "pending" | "approved" | "rejected" | "published" | "failed";
  created_at?: string | null;
  streamer: {
    id: string;
    display_name: string;
    platform: string;
    avatar_url?: string | null;
  };
  session: {
    title?: string | null;
    game_name?: string | null;
  };
  clip?: {
    id?: string;
    filename: string;
    duration: number;
    virality_score: number;
    hook_title?: string | null;
    post_text?: {
      hook?: string;
      title?: string;
      description?: string;
      hashtags?: string[];
      highlight_words?: string[];
    } | null;
  } | null;
};

type OverviewStats = {
  monitored_channels_count: number;
  currently_live_count: number;
  streams_processed_count: number;
  total_clips_count: number;
  clips_awaiting_approval: number;
  processing_errors_count: number;
};

const CATEGORY_LABELS: Record<string, { label: string; icon: string }> = {
  funny: { label: "Humor / Funny", icon: "😂" },
  loud_reaction: { label: "Loud Reaction", icon: "📢" },
  exciting_gameplay: { label: "Hype Gameplay", icon: "🎮" },
  conversation: { label: "Story / Dialogue", icon: "💬" },
  unexpected: { label: "Unexpected", icon: "⚡" },
  emotional: { label: "Emotional", icon: "💖" },
  highlight: { label: "Highlight", icon: "✨" },
};

export default function LiveDashboardPage() {
  const [stats, setStats] = useState<OverviewStats>({
    monitored_channels_count: 0,
    currently_live_count: 0,
    streams_processed_count: 0,
    total_clips_count: 0,
    clips_awaiting_approval: 0,
    processing_errors_count: 0,
  });
  const [channels, setChannels] = useState<MonitoredChannel[]>([]);
  const [moments, setMoments] = useState<LiveMoment[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>("all");

  // New channel form state
  const [newPlatform, setNewPlatform] = useState<"twitch" | "kick" | "youtube">("twitch");
  const [newChannel, setNewChannel] = useState("");
  const [newMaxClips, setNewMaxClips] = useState(5);
  const [newMinDuration, setNewMinDuration] = useState(20);
  const [newMaxDuration, setNewMaxDuration] = useState(60);
  const [addingChannel, setAddingChannel] = useState(false);

  // Clipboard copy tracker
  const [copiedMomentId, setCopiedMomentId] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    try {
      const [overviewRes, channelsRes, momentsRes] = await Promise.all([
        fetch("/api/live/overview"),
        fetch("/api/live/channels"),
        fetch("/api/live/moments"),
      ]);

      if (overviewRes.ok) {
        setStats(await overviewRes.json());
      }
      if (channelsRes.ok) {
        setChannels(await channelsRes.json());
      }
      if (momentsRes.ok) {
        setMoments(await momentsRes.json());
      }
    } catch (err) {
      console.error("Failed to load live engine data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
    // Poll updates every 12 seconds
    const interval = setInterval(fetchDashboardData, 12000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleManualPoll = async () => {
    setPolling(true);
    try {
      const res = await fetch("/api/live/poll", { method: "POST" });
      if (res.ok) {
        toast.success("Checked all monitored channels for live status");
        await fetchDashboardData();
      } else {
        toast.error("Failed to poll channels");
      }
    } catch {
      toast.error("Network error while polling");
    } finally {
      setPolling(false);
    }
  };

  const handleCheckChannel = async (channelId: string) => {
    try {
      const res = await fetch(`/api/live/channels/${channelId}/check`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.is_live) {
          toast.success(`${data.channel_identifier} is LIVE!`);
        } else {
          toast.info(`${data.channel_identifier} is currently offline.`);
        }
        await fetchDashboardData();
      } else {
        toast.error("Check failed");
      }
    } catch {
      toast.error("Network error");
    }
  };

  const handleToggleChannelActive = async (channel: MonitoredChannel) => {
    try {
      const res = await fetch(`/api/live/channels/${channel.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !channel.is_active }),
      });
      if (res.ok) {
        toast.success(channel.is_active ? "Channel paused" : "Channel monitoring active");
        await fetchDashboardData();
      }
    } catch {
      toast.error("Failed to update status");
    }
  };

  const handleDeleteChannel = async (channelId: string, name: string) => {
    if (!confirm(`Are you sure you want to stop monitoring ${name}?`)) return;
    try {
      const res = await fetch(`/api/live/channels/${channelId}`, { method: "DELETE" });
      if (res.ok) {
        toast.success(`Removed ${name}`);
        await fetchDashboardData();
      }
    } catch {
      toast.error("Failed to delete channel");
    }
  };

  const handleAddChannel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newChannel.trim()) {
      toast.error("Please enter a channel name or URL");
      return;
    }

    setAddingChannel(true);
    try {
      const res = await fetch("/api/live/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: newPlatform,
          channel: newChannel.trim(),
          max_clips_per_stream: newMaxClips,
          min_clip_duration: newMinDuration,
          max_clip_duration: newMaxDuration,
        }),
      });

      if (res.ok) {
        const created = await res.json();
        toast.success(`Added ${created.display_name} to monitoring!`);
        setNewChannel("");
        setAddModalOpen(false);
        await fetchDashboardData();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to add channel");
      }
    } catch {
      toast.error("Network error adding channel");
    } finally {
      setAddingChannel(false);
    }
  };

  const handleApproveMoment = async (momentId: string) => {
    try {
      const res = await fetch(`/api/live/moments/${momentId}/approve`, { method: "POST" });
      if (res.ok) {
        toast.success("Moment approved for publishing!");
        await fetchDashboardData();
      }
    } catch {
      toast.error("Failed to approve moment");
    }
  };

  const handleRejectMoment = async (momentId: string) => {
    try {
      const res = await fetch(`/api/live/moments/${momentId}/reject`, { method: "POST" });
      if (res.ok) {
        toast.info("Moment dismissed");
        await fetchDashboardData();
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
        await fetchDashboardData();
      } else {
        toast.error("Failed to delete moment");
      }
    } catch {
      toast.error("Network error deleting moment");
    }
  };

  const isActivelyRendering = (m: LiveMoment) => {
    if (m.clip_id || m.clip?.id) return false;
    if (m.status === "failed" || m.status === "rejected") return false;
    if (!m.created_at) return false;
    const createdTime = new Date(m.created_at).getTime();
    return Date.now() - createdTime < 180000;
  };

  const handleCopyPostText = (moment: LiveMoment) => {
    const pt = moment.clip?.post_text;
    if (!pt) {
      toast.error("No Post Text available for this moment");
      return;
    }

    const title = pt.title || moment.session.title || "Viral Clip";
    const desc = pt.description || "";
    const tags = (pt.hashtags || []).map((t) => `#${t.replace(/^#/, "")}`).join(" ");

    const formatted = [title, desc, tags].filter(Boolean).join("\n\n");
    navigator.clipboard.writeText(formatted);
    setCopiedMomentId(moment.id);
    toast.success("Post Text copied to clipboard!");
    setTimeout(() => setCopiedMomentId(null), 2500);
  };

  const filteredMoments = moments.filter((m) => {
    if (filterStatus === "all") return true;
    if (filterStatus === "pending") return m.status === "pending";
    if (filterStatus === "approved") return m.status === "approved";
    if (filterStatus === "rejected") return m.status === "rejected";
    return true;
  });

  return (
    <div className="min-h-screen bg-background text-foreground pb-20">
      {/* Top Header */}
      <div className="border-b border-border bg-card/40 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-red-500/10 border border-red-500/20 text-red-500">
                <Radio className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight">Live AI Clipping Engine</h1>
                <p className="text-sm text-muted-foreground">
                  Continuous 24/7 stream monitoring, AI hype detection, and automated 9:16 vertical clips.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handleManualPoll}
              disabled={polling}
              className="gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${polling ? "animate-spin" : ""}`} />
              Check Status
            </Button>

            <Dialog open={addModalOpen} onOpenChange={setAddModalOpen}>
              <DialogTrigger asChild>
                <Button size="sm" className="gap-2 bg-primary text-primary-foreground">
                  <Plus className="w-4 h-4" />
                  Add Streamer
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <form onSubmit={handleAddChannel}>
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <Tv className="w-5 h-5 text-primary" />
                      Monitor New Streamer
                    </DialogTitle>
                    <DialogDescription>
                      The AI engine will automatically detect when they go live, record recent buffers, and extract interesting moments.
                    </DialogDescription>
                  </DialogHeader>

                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Streaming Platform</Label>
                      <Select
                        value={newPlatform}
                        onValueChange={(val: "twitch" | "kick" | "youtube") => setNewPlatform(val)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select platform" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="twitch">🟣 Twitch</SelectItem>
                          <SelectItem value="kick">🟢 Kick</SelectItem>
                          <SelectItem value="youtube">🔴 YouTube Live</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>Channel Username or URL</Label>
                      <Input
                        placeholder={
                          newPlatform === "twitch"
                            ? "e.g. shroud or https://twitch.tv/shroud"
                            : newPlatform === "kick"
                            ? "e.g. xqc or https://kick.com/xqc"
                            : "e.g. @MrBeast or channel URL"
                        }
                        value={newChannel}
                        onChange={(e) => setNewChannel(e.target.value)}
                        required
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <Label>Max Clips Per Stream</Label>
                        <span className="font-semibold text-primary">{newMaxClips} clips</span>
                      </div>
                      <Slider
                        value={[newMaxClips]}
                        onValueChange={([val]) => setNewMaxClips(val)}
                        min={1}
                        max={15}
                        step={1}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <Label className="text-xs">Min Duration ({newMinDuration}s)</Label>
                        <Slider
                          value={[newMinDuration]}
                          onValueChange={([val]) => setNewMinDuration(val)}
                          min={15}
                          max={45}
                          step={5}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Max Duration ({newMaxDuration}s)</Label>
                        <Slider
                          value={[newMaxDuration]}
                          onValueChange={([val]) => setNewMaxDuration(val)}
                          min={30}
                          max={90}
                          step={5}
                        />
                      </div>
                    </div>
                  </div>

                  <DialogFooter>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setAddModalOpen(false)}
                      disabled={addingChannel}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" disabled={addingChannel}>
                      {addingChannel ? "Adding Channel..." : "Start Monitoring"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Overview Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card className="bg-card/50 border-border">
            <CardHeader className="p-4 pb-2">
              <CardDescription className="text-xs flex items-center justify-between">
                <span>Monitored</span>
                <Tv className="w-4 h-4 text-muted-foreground" />
              </CardDescription>
              <CardTitle className="text-2xl font-bold">{stats.monitored_channels_count}</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground">Active streamer channels</CardContent>
          </Card>

          <Card className="bg-card/50 border-border">
            <CardHeader className="p-4 pb-2">
              <CardDescription className="text-xs flex items-center justify-between">
                <span>Live Now</span>
                <span className="relative flex h-2 w-2">
                  {stats.currently_live_count > 0 && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  )}
                  <span
                    className={`relative inline-flex rounded-full h-2 w-2 ${
                      stats.currently_live_count > 0 ? "bg-emerald-500" : "bg-zinc-600"
                    }`}
                  ></span>
                </span>
              </CardDescription>
              <CardTitle className="text-2xl font-bold text-emerald-400">
                {stats.currently_live_count}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground">Streaming right now</CardContent>
          </Card>

          <Card className="bg-card/50 border-border">
            <CardHeader className="p-4 pb-2">
              <CardDescription className="text-xs flex items-center justify-between">
                <span>Streams Logged</span>
                <Clock className="w-4 h-4 text-muted-foreground" />
              </CardDescription>
              <CardTitle className="text-2xl font-bold">{stats.streams_processed_count}</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground">Total broadcast sessions</CardContent>
          </Card>

          <Card className="bg-card/50 border-border">
            <CardHeader className="p-4 pb-2">
              <CardDescription className="text-xs flex items-center justify-between">
                <span>Clips Cut</span>
                <Sparkles className="w-4 h-4 text-primary" />
              </CardDescription>
              <CardTitle className="text-2xl font-bold text-primary">{stats.total_clips_count}</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground">Shorts & Reels generated</CardContent>
          </Card>

          <Card className="bg-card/50 border-border">
            <CardHeader className="p-4 pb-2">
              <CardDescription className="text-xs flex items-center justify-between">
                <span>Awaiting Review</span>
                <Flame className="w-4 h-4 text-amber-500" />
              </CardDescription>
              <CardTitle className="text-2xl font-bold text-amber-400">
                {stats.clips_awaiting_approval}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground">Pending publishing approval</CardContent>
          </Card>
        </div>

        {/* Dashboard Tabs */}
        <Tabs defaultValue="moments" className="space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <TabsList className="bg-card border border-border">
              <TabsTrigger value="moments" className="gap-2">
                <Sparkles className="w-4 h-4" />
                Generated Clips
                {stats.clips_awaiting_approval > 0 && (
                  <Badge variant="secondary" className="ml-1 text-xs px-1.5 py-0 bg-amber-500/20 text-amber-400">
                    {stats.clips_awaiting_approval}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="channels" className="gap-2">
                <Tv className="w-4 h-4" />
                Live Channels ({channels.length})
              </TabsTrigger>
            </TabsList>
          </div>

          {/* TAB 1: GENERATED CLIPS (THE APPROVAL WALL) */}
          <TabsContent value="moments" className="space-y-4">
            {/* Filter buttons */}
            <div className="flex gap-2">
              {["all", "pending", "approved", "rejected"].map((st) => (
                <Button
                  key={st}
                  variant={filterStatus === st ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFilterStatus(st)}
                  className="capitalize text-xs h-7"
                >
                  {st === "pending" ? "Awaiting Approval" : st}
                </Button>
              ))}
            </div>

            {loading ? (
              <div className="p-12 text-center text-muted-foreground">Loading generated clips...</div>
            ) : filteredMoments.length === 0 ? (
              <Card className="p-12 text-center border-dashed border-border bg-card/30">
                <div className="max-w-md mx-auto space-y-3">
                  <div className="p-3 bg-muted rounded-full w-fit mx-auto text-muted-foreground">
                    <Radio className="w-6 h-6" />
                  </div>
                  <h3 className="font-semibold text-lg">
                    {moments.length > 0
                      ? `No ${filterStatus === "pending" ? "pending" : filterStatus} clips`
                      : "No Clips Yet"}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {moments.length > 0
                      ? `You have ${moments.length} total clip${moments.length === 1 ? "" : "s"} under other filters.`
                      : "When your monitored streamers go live, the AI engine listens to their audio energy and dialogue to automatically cut and reframe vertical clips."}
                  </p>
                  {moments.length > 0 ? (
                    <Button variant="outline" size="sm" onClick={() => setFilterStatus("all")}>
                      View All Clips ({moments.length})
                    </Button>
                  ) : channels.length === 0 ? (
                    <Button onClick={() => setAddModalOpen(true)} className="gap-2">
                      <Plus className="w-4 h-4" /> Add Your First Streamer
                    </Button>
                  ) : null}
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredMoments.map((moment) => {
                  const pt = moment.clip?.post_text;
                  const cat = CATEGORY_LABELS[moment.category] || CATEGORY_LABELS.highlight;

                  return (
                    <Card key={moment.id} className="bg-card border-border overflow-hidden flex flex-col justify-between">
                      {/* Video Player or Placeholder */}
                      <div className="relative aspect-[9/16] max-h-[380px] w-full bg-black/80 flex items-center justify-center overflow-hidden border-b border-border">
                        {moment.task_id && (moment.clip_id || moment.clip?.id) ? (
                          <video
                            controls
                            className="w-full h-full object-contain"
                            src={`/api/tasks/${moment.task_id}/clips/${moment.clip_id || moment.clip?.id}/file`}
                          />
                        ) : isActivelyRendering(moment) ? (
                          <div className="text-center p-4 space-y-2 text-muted-foreground">
                            <RefreshCw className="w-7 h-7 mx-auto text-primary animate-spin" />
                            <p className="text-xs font-semibold text-foreground">Rendering Vertical Clip...</p>
                            <p className="text-[10px] text-muted-foreground">Usually takes 15–30 seconds</p>
                          </div>
                        ) : (
                          <div className="text-center p-4 space-y-2 text-muted-foreground">
                            <AlertTriangle className="w-6 h-6 mx-auto text-amber-500/80" />
                            <p className="text-xs font-semibold text-foreground">Clip Unavailable</p>
                            <p className="text-[10px] text-muted-foreground max-w-[200px]">
                              Stream buffer segment expired or render incomplete
                            </p>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-[11px] h-7 text-destructive hover:bg-destructive/10"
                              onClick={() => handleDeleteMoment(moment.id)}
                            >
                              <Trash2 className="w-3 h-3 mr-1" /> Remove
                            </Button>
                          </div>
                        )}

                        {/* Top Overlays */}
                        <div className="absolute top-3 left-3 flex items-center gap-2">
                          <Badge className="bg-black/70 backdrop-blur-md text-xs border border-white/10 gap-1">
                            <span>{cat.icon}</span>
                            <span>{cat.label}</span>
                          </Badge>
                        </div>

                        {moment.clip?.virality_score ? (
                          <div className="absolute top-3 right-3">
                            <Badge className="bg-emerald-500/90 text-white font-mono text-xs">
                              {moment.clip.virality_score} Virality
                            </Badge>
                          </div>
                        ) : null}
                      </div>

                      {/* Content Body */}
                      <div className="p-4 space-y-4 flex-1 flex flex-col justify-between">
                        <div className="space-y-2">
                          {/* Streamer Header */}
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span className="font-medium text-foreground flex items-center gap-1.5">
                              {moment.streamer.avatar_url && (
                                <img
                                  src={moment.streamer.avatar_url}
                                  alt={moment.streamer.display_name}
                                  className="w-[18px] h-[18px] rounded-full object-cover"
                                />
                              )}
                              {moment.streamer.display_name}
                            </span>
                            <Badge variant="outline" className="capitalize text-[10px]">
                              {moment.streamer.platform}
                            </Badge>
                          </div>

                          <h4 className="font-semibold text-sm line-clamp-2">
                            {moment.clip?.hook_title || moment.description || "Exciting Live Moment"}
                          </h4>

                          {/* PeakCut Post Text Module */}
                          {pt && (
                            <div className="p-2.5 rounded-lg bg-muted/40 border border-border/80 space-y-1.5 text-xs">
                              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                                <span className="flex items-center gap-1 text-primary font-medium">
                                  <Sparkles className="w-3 h-3" /> Post Text
                                </span>
                                <button
                                  onClick={() => handleCopyPostText(moment)}
                                  className="flex items-center gap-1 hover:text-foreground transition-colors font-medium text-[11px]"
                                >
                                  {copiedMomentId === moment.id ? (
                                    <>
                                      <Check className="w-3 h-3 text-emerald-400" /> Copied!
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="w-3 h-3" /> Copy
                                    </>
                                  )}
                                </button>
                              </div>

                              {pt.hook && (
                                <div className="font-bold text-amber-300 text-[11px] tracking-wide">
                                  {pt.hook}
                                </div>
                              )}
                              {pt.title && <div className="font-medium text-foreground text-xs">{pt.title}</div>}
                              {pt.description && (
                                <p className="text-muted-foreground text-[11px] line-clamp-2">{pt.description}</p>
                              )}
                              {pt.hashtags && pt.hashtags.length > 0 && (
                                <div className="text-[10px] text-primary/80 line-clamp-1">
                                  {pt.hashtags.map((h) => `#${h}`).join(" ")}
                                </div>
                              )}
                            </div>
                          )}

                          {moment.reason && (
                            <p className="text-xs text-muted-foreground italic line-clamp-2">
                              💡 AI Reason: {moment.reason}
                            </p>
                          )}
                        </div>

                        {/* Action Buttons */}
                        <div className="pt-3 border-t border-border flex flex-col gap-2">
                          {moment.status === "pending" && (
                            <div className="grid grid-cols-2 gap-2">
                              <Button
                                size="sm"
                                className="bg-emerald-600 hover:bg-emerald-500 text-white gap-1 text-xs h-8"
                                onClick={() => handleApproveMoment(moment.id)}
                              >
                                <Check className="w-3.5 h-3.5" /> Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-red-500/30 text-red-400 hover:bg-red-500/10 text-xs h-8"
                                onClick={() => handleRejectMoment(moment.id)}
                              >
                                <X className="w-3.5 h-3.5" /> Reject
                              </Button>
                            </div>
                          )}

                          <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
                            <Badge
                              variant="secondary"
                              className={`capitalize text-[10px] ${
                                moment.status === "approved"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : moment.status === "pending"
                                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                  : "text-muted-foreground"
                              }`}
                            >
                              {moment.status}
                            </Badge>

                            <div className="flex items-center gap-2">
                              {moment.task_id && (
                                <Link
                                  href={`/tasks/${moment.task_id}/edit`}
                                  className="hover:text-foreground flex items-center gap-1"
                                >
                                  Editor <ExternalLink className="w-3 h-3" />
                                </Link>
                              )}
                              {moment.task_id && (moment.clip_id || moment.clip?.id) && (
                                <a
                                  href={`/api/tasks/${moment.task_id}/clips/${moment.clip_id || moment.clip?.id}/file`}
                                  download
                                  className="hover:text-foreground"
                                  title="Download MP4"
                                >
                                  <Download className="w-3.5 h-3.5" />
                                </a>
                              )}
                              <button
                                onClick={() => handleDeleteMoment(moment.id)}
                                className="hover:text-destructive text-muted-foreground transition-colors"
                                title="Delete moment"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          {/* TAB 2: MONITORED CHANNELS */}
          <TabsContent value="channels" className="space-y-4">
            {channels.length === 0 ? (
              <Card className="p-8 text-center border-dashed border-border">
                <p className="text-muted-foreground text-sm">No streamers registered yet.</p>
                <Button size="sm" onClick={() => setAddModalOpen(true)} className="mt-3 gap-2">
                  <Plus className="w-4 h-4" /> Add Streamer
                </Button>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {channels.map((ch) => {
                  const isLive = ch.status === "live";

                  return (
                    <Card key={ch.id} className="bg-card border-border overflow-hidden">
                      <CardHeader className="p-4 pb-2">
                        <div className="flex items-start justify-between gap-3">
                          <Link href={`/live/${ch.id}`} className="flex items-center gap-3 group/link min-w-0">
                            {ch.avatar_url ? (
                              <img
                                src={ch.avatar_url}
                                alt={ch.display_name}
                                className="w-10 h-10 rounded-full border border-border group-hover/link:ring-2 ring-primary/40 transition-all object-cover"
                              />
                            ) : (
                              <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center font-bold text-primary group-hover/link:ring-2 ring-primary/40 transition-all">
                                {ch.display_name.slice(0, 2).toUpperCase()}
                              </div>
                            )}
                            <div className="min-w-0">
                              <CardTitle className="text-base font-bold flex items-center gap-2 group-hover/link:text-primary transition-colors truncate">
                                {ch.display_name}
                                <Badge variant="outline" className="text-[10px] uppercase shrink-0">
                                  {ch.platform}
                                </Badge>
                              </CardTitle>
                              <CardDescription className="text-xs font-mono truncate">
                                {ch.channel_identifier}
                              </CardDescription>
                            </div>
                          </Link>

                          {/* Status Pill */}
                          {isLive ? (
                            <Badge className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 gap-1.5 animate-pulse text-xs">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                              LIVE
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-xs text-muted-foreground uppercase">
                              {ch.status}
                            </Badge>
                          )}
                        </div>
                      </CardHeader>

                      <CardContent className="p-4 pt-2 space-y-3">
                        {isLive && ch.active_session && (
                          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-1 text-xs">
                            <div className="font-semibold text-emerald-300 line-clamp-1">
                              {ch.active_session.title || "Live Stream Broadcast"}
                            </div>
                            {ch.active_session.game_name && (
                              <div className="text-[11px] text-emerald-400/80">
                                Category: {ch.active_session.game_name}
                              </div>
                            )}
                          </div>
                        )}

                        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground py-1">
                          <div>
                            <span className="block text-[10px] uppercase font-semibold">Clips Extracted</span>
                            <span className="font-bold text-foreground text-sm">{ch.clips_count}</span>
                          </div>
                          <div>
                            <span className="block text-[10px] uppercase font-semibold">Duration Limit</span>
                            <span className="font-medium text-foreground">
                              {ch.min_clip_duration}s – {ch.max_clip_duration}s
                            </span>
                          </div>
                        </div>

                        {ch.last_error && (
                          <div className="text-xs text-red-400 flex items-center gap-1.5 bg-red-500/10 p-2 rounded border border-red-500/20">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            <span className="line-clamp-1">{ch.last_error}</span>
                          </div>
                        )}

                        {/* Stream Studio Preview Button */}
                        <Button asChild size="sm" variant="outline" className="w-full gap-2 text-xs h-8">
                          <Link href={`/live/${ch.id}`}>
                            <Tv className="w-3.5 h-3.5 text-primary" />
                            <span>Preview Stream & Studio</span>
                            <ExternalLink className="w-3 h-3 ml-auto opacity-50" />
                          </Link>
                        </Button>

                        {/* Channel Controls */}
                        <div className="pt-2 border-t border-border flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Switch
                              checked={ch.is_active}
                              onCheckedChange={() => handleToggleChannelActive(ch)}
                            />
                            <span className="text-xs text-muted-foreground">
                              {ch.is_active ? "Active" : "Paused"}
                            </span>
                          </div>

                          <div className="flex items-center gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleCheckChannel(ch.id)}
                              title="Check status now"
                              className="h-8 w-8 p-0"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleDeleteChannel(ch.id, ch.display_name)}
                              className="h-8 w-8 p-0 text-red-400 hover:text-red-300"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
