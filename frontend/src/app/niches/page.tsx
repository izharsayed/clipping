/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Check,
  Clapperboard,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Flame,
  Gamepad2,
  HelpCircle,
  Mic,
  RefreshCw,
  Sliders,
  Sparkles,
  SplitSquareVertical,
  Trophy,
  Video,
  Volume2,
  Wand2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

type NicheMeta = {
  id: string;
  name: string;
  tagline: string;
  icon: string;
  badge: string;
  avg_views: string;
  description: string;
  difficulty: string;
  recommended_length: string;
};

type NicheTemplatesData = {
  niches: NicheMeta[];
  plans: Record<string, any>;
  voices: string[];
};

type RenderResult = {
  task_id: string;
  clip_id: string;
  filename: string;
  duration: number;
  video_url: string;
  cover_url?: string;
  post_text: {
    title: string;
    caption: string;
    hashtags: string[];
    formatted_copy: string;
    hook?: string;
  };
  qc: {
    loudness_lufs: number;
    resolution: string;
    fps: number;
    compliance: string;
  };
};

const NICHE_ICONS: Record<string, any> = {
  commentary: Mic,
  compare: SplitSquareVertical,
  stunts: Zap,
  myths: HelpCircle,
  moments: Flame,
  rank: Trophy,
  skit: Clapperboard,
};

export default function NichesStudioPage() {
  const [data, setData] = useState<NicheTemplatesData | null>(null);
  const [selectedNiche, setSelectedNiche] = useState<string>("commentary");
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [renderResult, setRenderResult] = useState<RenderResult | null>(null);
  const [recentClips, setRecentClips] = useState<any[]>([]);
  const [copied, setCopied] = useState(false);

  // Form State
  const [projectName, setProjectName] = useState("GTA 6 File Size");
  const [activePlan, setActivePlan] = useState<any>(null);
  const [previewingVoice, setPreviewingVoice] = useState(false);

  const fetchTemplates = useCallback(async () => {
    try {
      const [tplRes, recentRes] = await Promise.all([
        fetch("/api/niches/templates"),
        fetch("/api/niches/recent"),
      ]);

      if (tplRes.ok) {
        const d: NicheTemplatesData = await tplRes.json();
        setData(d);
        if (d.plans && d.plans["commentary"]) {
          setActivePlan(JSON.parse(JSON.stringify(d.plans["commentary"])));
          setProjectName(d.plans["commentary"].name || "GTA 6 File Size");
        }
      }

      if (recentRes.ok) {
        setRecentClips(await recentRes.json());
      }
    } catch (err) {
      console.error("Failed to load niche templates:", err);
      toast.error("Could not connect to Niche Studio backend");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleSelectNiche = (nicheId: string) => {
    setSelectedNiche(nicheId);
    if (data?.plans && data.plans[nicheId]) {
      const p = JSON.parse(JSON.stringify(data.plans[nicheId]));
      setActivePlan(p);
      setProjectName(p.name || `My ${data.niches.find((n) => n.id === nicheId)?.name}`);
    }
  };

  const handlePreviewVoice = async () => {
    if (!activePlan?.script) return;
    setPreviewingVoice(true);
    try {
      const res = await fetch("/api/niches/preview-voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: activePlan.script,
          voice: activePlan.voice || "am_michael",
          speed: activePlan.voice_speed || 1.05,
        }),
      });

      if (!res.ok) throw new Error("Voice synthesis preview failed");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
      toast.success("Playing voice preview");
    } catch (err: any) {
      toast.error(err.message || "Voice preview error");
    } finally {
      setPreviewingVoice(false);
    }
  };

  const handleRender = async () => {
    if (!activePlan) return;
    setRendering(true);
    setRenderResult(null);
    try {
      const payload = {
        niche: selectedNiche,
        name: projectName || "Viral Gaming Short",
        plan: activePlan,
      };

      const res = await fetch("/api/niches/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Video render failed");
      }

      const result: RenderResult = await res.json();
      setRenderResult(result);
      toast.success(`Rendered 9:16 Short (${result.duration}s)! Normalization: -14 LUFS`);

      // Refresh recent list
      const recentRes = await fetch("/api/niches/recent");
      if (recentRes.ok) setRecentClips(await recentRes.json());
    } catch (err: any) {
      toast.error(err.message || "Rendering failed");
    } finally {
      setRendering(false);
    }
  };

  const handleCopyPostKit = () => {
    if (!renderResult?.post_text?.formatted_copy) return;
    navigator.clipboard.writeText(renderResult.post_text.formatted_copy);
    setCopied(true);
    toast.success("Post Kit (Title, Description, & Hashtags) copied!");
    setTimeout(() => setCopied(false), 2500);
  };

  const currentNicheMeta = useMemo(() => {
    return data?.niches.find((n) => n.id === selectedNiche) || null;
  }, [data, selectedNiche]);

  return (
    <div className="min-h-screen bg-background text-foreground pb-24">
      {/* Studio Header */}
      <div className="border-b border-border bg-card/40 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg text-primary">
                <Gamepad2 className="w-6 h-6" />
              </div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight">Gaming Niche Studio</h1>
              <Badge variant="outline" className="border-primary/40 text-primary bg-primary/5 text-xs">
                7 Viral Formulas
              </Badge>
              {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
            </div>
            <p className="text-xs md:text-sm text-muted-foreground">
              Turn gameplay into finished 9:16 vertical Shorts with AI voiceovers, split-screens, and broadcast -14 LUFS loudness.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSelectNiche(selectedNiche)}
              className="gap-2 text-xs"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Reset Template
            </Button>
            <Button
              onClick={handleRender}
              disabled={rendering || !activePlan}
              className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold shadow-lg shadow-primary/20 text-xs md:text-sm"
            >
              {rendering ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" /> Rendering Short...
                </>
              ) : (
                <>
                  <Wand2 className="w-4 h-4" /> Render 9:16 Short
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Niche Selector Cards Grid */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            1. Select a Proven Viral Gaming Niche
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {data?.niches.map((n) => {
              const IconComp = NICHE_ICONS[n.id] || Sparkles;
              const isSelected = selectedNiche === n.id;
              return (
                <Card
                  key={n.id}
                  onClick={() => handleSelectNiche(n.id)}
                  className={`cursor-pointer transition-all hover:border-primary/60 border ${
                    isSelected ? "border-primary bg-primary/5 ring-1 ring-primary/40 shadow-md" : "border-border bg-card"
                  }`}
                >
                  <CardHeader className="p-4 pb-2">
                    <div className="flex items-center justify-between">
                      <div className={`p-2 rounded-lg ${isSelected ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}>
                        <IconComp className="w-4 h-4" />
                      </div>
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                        {n.badge}
                      </Badge>
                    </div>
                    <CardTitle className="text-sm font-bold mt-2">{n.name}</CardTitle>
                    <CardDescription className="text-xs line-clamp-2">{n.tagline}</CardDescription>
                  </CardHeader>
                  <CardContent className="p-4 pt-1 flex items-center justify-between text-[11px] text-muted-foreground border-t border-border/40 mt-2">
                    <span>{n.recommended_length}</span>
                    <span className="font-mono text-emerald-400 font-semibold">{n.avg_views}</span>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>

        {/* Studio Workspace: Form Config & Live Preview */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left: Configuration Form */}
          <div className="lg:col-span-7 space-y-6">
            <Card className="border-border bg-card">
              <CardHeader className="pb-4 border-b border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-bold flex items-center gap-2">
                      <Sliders className="w-4 h-4 text-primary" />
                      {currentNicheMeta?.name || "Niche Settings"}
                    </CardTitle>
                    <CardDescription className="text-xs">
                      {currentNicheMeta?.description}
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="p-6 space-y-6">
                {/* Project Title */}
                <div className="space-y-2">
                  <Label className="text-xs font-semibold">Video Name & Project Title</Label>
                  <Input
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="e.g. GTA 6 File Size Is Insane"
                    className="bg-background"
                  />
                </div>

                {/* Niche Specific Form Controls */}
                {selectedNiche === "commentary" && activePlan && (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs font-semibold">Voiceover Script & Image Triggers</Label>
                        <span className="text-[11px] text-muted-foreground font-mono">Use {"{pic:id}"} to trigger pop-ups</span>
                      </div>
                      <Textarea
                        rows={4}
                        value={activePlan.script || ""}
                        onChange={(e) => setActivePlan({ ...activePlan, script: e.target.value })}
                        placeholder="Type script... Use {pic:id} right before a keyword to trigger a graphic card"
                        className="bg-background text-sm font-sans"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">AI Neural Voice</Label>
                        <Select
                          value={activePlan.voice || "am_michael"}
                          onValueChange={(val) => setActivePlan({ ...activePlan, voice: val })}
                        >
                          <SelectTrigger className="bg-background">
                            <SelectValue placeholder="Select voice" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="am_michael">Michael (US Energetic)</SelectItem>
                            <SelectItem value="am_adam">Adam (US Deep/Story)</SelectItem>
                            <SelectItem value="af_bella">Bella (US Expressive)</SelectItem>
                            <SelectItem value="af_nicole">Nicole (US Smooth)</SelectItem>
                            <SelectItem value="bm_george">George (British Narrator)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">Speech Speed</Label>
                        <Select
                          value={String(activePlan.voice_speed || 1.05)}
                          onValueChange={(val) => setActivePlan({ ...activePlan, voice_speed: parseFloat(val) })}
                        >
                          <SelectTrigger className="bg-background">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="0.95">0.95x (Chill)</SelectItem>
                            <SelectItem value="1.0">1.0x (Normal)</SelectItem>
                            <SelectItem value="1.05">1.05x (YouTube Fast)</SelectItem>
                            <SelectItem value="1.15">1.15x (Hyper Paced)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handlePreviewVoice}
                      disabled={previewingVoice || !activePlan.script}
                      className="gap-2 text-xs"
                    >
                      {previewingVoice ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Volume2 className="w-3.5 h-3.5 text-primary" />}
                      Test Speech Cadence
                    </Button>
                  </div>
                )}

                {selectedNiche === "compare" && activePlan && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">Top Label (Pill)</Label>
                        <Input
                          value={activePlan.top_label || "GTA 6"}
                          onChange={(e) => setActivePlan({ ...activePlan, top_label: e.target.value })}
                          placeholder="e.g. GTA 6"
                          className="bg-background"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">Bottom Label (Pill)</Label>
                        <Input
                          value={activePlan.bottom_label || "GTA 5"}
                          onChange={(e) => setActivePlan({ ...activePlan, bottom_label: e.target.value })}
                          placeholder="e.g. GTA 5"
                          className="bg-background"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold">Audio Channel</Label>
                      <Select
                        value={activePlan.audio || "top"}
                        onValueChange={(val) => setActivePlan({ ...activePlan, audio: val })}
                      >
                        <SelectTrigger className="bg-background">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="top">Top Game Audio Only</SelectItem>
                          <SelectItem value="bottom">Bottom Game Audio Only</SelectItem>
                          <SelectItem value="both">Mix Both Sounds</SelectItem>
                          <SelectItem value="none">Mute Both (Music only)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}

                {selectedNiche === "stunts" && activePlan && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">Failed Attempts to Show</Label>
                        <Input
                          type="number"
                          value={activePlan.fails?.length || 3}
                          onChange={(e) => {
                            const count = parseInt(e.target.value) || 3;
                            const newFails = Array.from({ length: count }, (_, i) => ({ n: i + 1, a: i * 3.5, b: (i + 1) * 3.5 }));
                            setActivePlan({ ...activePlan, fails: newFails });
                          }}
                          className="bg-background"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold">Landed Attempt Number</Label>
                        <Input
                          type="number"
                          value={activePlan.landed?.n || 69}
                          onChange={(e) => setActivePlan({ ...activePlan, landed: { ...activePlan.landed, n: parseInt(e.target.value) || 69 } })}
                          className="bg-background"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between border border-border p-3 rounded-lg bg-background/50">
                      <div>
                        <Label className="text-xs font-semibold">Slow-Motion Landing Replay</Label>
                        <p className="text-[11px] text-muted-foreground">Appends an instant 0.5x slow-mo breakdown with badge</p>
                      </div>
                      <Switch
                        checked={Boolean(activePlan.replay)}
                        onCheckedChange={(checked) => setActivePlan({ ...activePlan, replay: checked ? { speed: 0.5, zoom: 1.1 } : null })}
                      />
                    </div>
                  </div>
                )}

                {selectedNiche === "myths" && activePlan && (
                  <div className="space-y-4">
                    <Label className="text-xs font-semibold">Myth Questions & Verdict Stamps</Label>
                    {activePlan.myths?.map((m: any, idx: number) => (
                      <div key={idx} className="p-3 border border-border rounded-lg bg-background space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-primary">Myth #{idx + 1}</span>
                          <Select
                            value={m.verdict || "BUSTED"}
                            onValueChange={(val) => {
                              const list = [...activePlan.myths];
                              list[idx].verdict = val;
                              setActivePlan({ ...activePlan, myths: list });
                            }}
                          >
                            <SelectTrigger className="h-7 w-32 text-xs font-bold">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="BUSTED" className="text-red-400 font-bold">BUSTED (Red)</SelectItem>
                              <SelectItem value="CONFIRMED" className="text-emerald-400 font-bold">CONFIRMED (Green)</SelectItem>
                              <SelectItem value="PATCHED" className="text-amber-400 font-bold">PATCHED (Yellow)</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <Input
                          value={m.question}
                          onChange={(e) => {
                            const list = [...activePlan.myths];
                            list[idx].question = e.target.value;
                            setActivePlan({ ...activePlan, myths: list });
                          }}
                          className="text-xs"
                          placeholder="e.g. Can you stop the train with tanks?"
                        />
                      </div>
                    ))}
                  </div>
                )}

                {selectedNiche === "rank" && activePlan && (
                  <div className="space-y-3">
                    <Label className="text-xs font-semibold">5-to-1 Countdown Items</Label>
                    {activePlan.items?.map((it: any, idx: number) => (
                      <div key={idx} className="flex items-center gap-3">
                        <Badge variant="secondary" className="w-8 text-center font-bold font-mono">
                          #{it.rank}
                        </Badge>
                        <Input
                          value={it.label}
                          onChange={(e) => {
                            const list = [...activePlan.items];
                            list[idx].label = e.target.value;
                            setActivePlan({ ...activePlan, items: list });
                          }}
                          className="text-xs bg-background"
                          placeholder={`Rank #${it.rank} label`}
                        />
                      </div>
                    ))}
                  </div>
                )}

                {/* Safe 9:16 Framing Controls */}
                <div className="pt-4 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-emerald-400" />
                    <span>Auto 1080x1920 (9:16) Safe Crop with Facecam Exclusion</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-emerald-400" />
                    <span>Broadcast -14 LUFS Audio Normalizer</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right: Render Result Preview & Post Kit */}
          <div className="lg:col-span-5 space-y-6">
            <Card className="border-border bg-card overflow-hidden">
              <CardHeader className="p-4 pb-3 border-b border-border">
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <Video className="w-4 h-4 text-primary" />
                  9:16 Vertical Video Preview
                </CardTitle>
                <CardDescription className="text-xs">
                  {renderResult ? "Ready for YouTube Shorts, TikTok & Reels" : "Your rendered vertical Short will appear here"}
                </CardDescription>
              </CardHeader>

              <CardContent className="p-4 space-y-4">
                <div className="relative aspect-[9/16] max-h-[460px] mx-auto w-full bg-black/90 rounded-xl overflow-hidden border border-border flex items-center justify-center">
                  {renderResult ? (
                    <video
                      controls
                      autoPlay
                      loop
                      className="w-full h-full object-contain"
                      src={renderResult.video_url}
                    />
                  ) : rendering ? (
                    <div className="text-center p-6 space-y-3 text-muted-foreground">
                      <RefreshCw className="w-8 h-8 animate-spin text-primary mx-auto" />
                      <p className="text-sm font-semibold text-foreground">Compositing 9:16 Short...</p>
                      <p className="text-xs">Applying spring animation cards and -14 LUFS normalization.</p>
                    </div>
                  ) : (
                    <div className="text-center p-6 space-y-2 text-muted-foreground">
                      <Gamepad2 className="w-10 h-10 mx-auto opacity-30" />
                      <p className="text-xs font-medium">Click &quot;Render 9:16 Short&quot; above to build your video.</p>
                    </div>
                  )}

                  {renderResult && (
                    <div className="absolute top-3 left-3">
                      <Badge className="bg-emerald-500/90 text-white text-xs font-mono shadow-md">
                        -14 LUFS Certified
                      </Badge>
                    </div>
                  )}
                </div>

                {/* Post Text Kit */}
                {renderResult && (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-semibold">Post Kit (SEO & Social Copy)</Label>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleCopyPostKit}
                        className="h-7 text-xs gap-1.5 text-primary hover:text-primary"
                      >
                        {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        {copied ? "Copied" : "Copy Kit"}
                      </Button>
                    </div>

                    <div className="p-3 bg-muted/60 rounded-lg text-xs space-y-2 font-sans border border-border">
                      <p className="font-bold text-foreground">{renderResult.post_text.title}</p>
                      <p className="text-muted-foreground">{renderResult.post_text.caption}</p>
                      <div className="flex flex-wrap gap-1 pt-1">
                        {renderResult.post_text.hashtags?.map((t: string) => (
                          <span key={t} className="text-primary font-mono text-[11px]">#{t.replace(/^#/, "")}</span>
                        ))}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button asChild variant="outline" size="sm" className="w-full gap-2 text-xs">
                        <a href={renderResult.video_url} download={renderResult.filename}>
                          <Download className="w-3.5 h-3.5" /> Download MP4
                        </a>
                      </Button>
                      <Button asChild size="sm" className="w-full gap-2 text-xs">
                        <Link href={`/editor/${renderResult.task_id}`}>
                          <ExternalLink className="w-3.5 h-3.5" /> Open in Editor
                        </Link>
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Recent Niche Shorts Gallery */}
        {recentClips.length > 0 && (
          <div className="space-y-4 pt-6 border-t border-border">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold flex items-center gap-2">
                <Clock className="w-4 h-4 text-primary" /> Recent Gaming Niche Shorts
              </h2>
              <Badge variant="outline" className="text-xs">{recentClips.length} Shorts Generated</Badge>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {recentClips.map((clip) => (
                <Card key={clip.clip_id} className="border-border bg-card overflow-hidden group">
                  <div className="relative aspect-[9/16] bg-black/80 flex items-center justify-center">
                    <video
                      controls
                      className="w-full h-full object-contain"
                      src={clip.video_url}
                    />
                    <div className="absolute top-2 left-2">
                      <Badge className="bg-black/70 backdrop-blur-md text-[10px] uppercase">
                        {clip.niche}
                      </Badge>
                    </div>
                  </div>
                  <CardContent className="p-3 space-y-2">
                    <p className="text-xs font-bold truncate">{clip.post_text?.title || clip.filename}</p>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>{clip.duration}s</span>
                      <span className="font-mono text-emerald-400 font-semibold">{clip.loudness_lufs} LUFS</span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
