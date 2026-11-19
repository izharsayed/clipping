"use client";

import { useEffect, useState, useMemo } from "react";
import { 
  Sparkles, 
  Coins, 
  Zap, 
  Layers, 
  Clock, 
  Activity, 
  Cpu, 
  Calendar,
  AlertCircle
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface TimeseriesPoint {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

interface BreakdownItem {
  provider?: string;
  feature?: string;
  tokens: number;
  cost_usd: number;
  requests: number;
}

interface RecentEvent {
  id: string;
  provider: string;
  model: string;
  feature: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  created_at: string | null;
}

interface TokenUsageSummary {
  period_days: number;
  active_provider: string;
  active_model: string;
  summary: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    total_cost_usd: number;
    total_requests: number;
  };
  by_provider: BreakdownItem[];
  by_feature: BreakdownItem[];
  timeseries: TimeseriesPoint[];
  recent_events: RecentEvent[];
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat().format(num);
}

function formatCost(cost: number): string {
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function formatFeatureName(feature: string): string {
  switch (feature) {
    case "clipping":
      return "Video Clipping & Analysis";
    case "post_text":
      return "PeakCut Post Text";
    case "live_moment":
      return "Live Stream Detection";
    case "workflow":
      return "Workflow Outlines";
    case "editor":
      return "AI Studio Edits";
    default:
      return feature.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

function featureBadgeColor(feature: string): string {
  switch (feature) {
    case "clipping":
      return "bg-blue-500/10 text-blue-500 border-blue-500/20";
    case "post_text":
      return "bg-amber-500/10 text-amber-500 border-amber-500/20";
    case "live_moment":
      return "bg-purple-500/10 text-purple-500 border-purple-500/20";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function ApiUsageDashboard() {
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<TokenUsageSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchUsage = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/token-usage?days=${days}`);
        if (!res.ok) {
          throw new Error(`Failed to load token usage (${res.status})`);
        }
        const json = await res.json();
        if (active) {
          setData(json);
        }
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load usage data");
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    fetchUsage();
    return () => {
      active = false;
    };
  }, [days]);

  const maxDailyTokens = useMemo(() => {
    if (!data?.timeseries?.length) return 1;
    return Math.max(...data.timeseries.map((p) => p.total_tokens), 1);
  }, [data?.timeseries]);

  const activeProviderName = useMemo(() => {
    const raw = data?.active_provider?.toLowerCase() || "google";
    if (raw.includes("google")) return "Google AI API (Gemini)";
    if (raw.includes("openai")) return "OpenAI";
    if (raw.includes("anthropic")) return "Anthropic (Claude)";
    if (raw.includes("openrouter")) return "OpenRouter";
    if (raw.includes("ollama")) return "Local Ollama";
    return raw.toUpperCase();
  }, [data?.active_provider]);

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Top Banner: Connected Provider & Range Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border bg-card/60 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-sm">
            <Cpu className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight">Connected AI Provider</h2>
              <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-[11px] gap-1 px-2 py-0.5">
                <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Active
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 font-medium">
              {activeProviderName} · <span className="font-mono text-foreground/80">{data?.active_model || "gemini-1.5-flash"}</span>
            </p>
          </div>
        </div>

        {/* Days Filter */}
        <div className="flex items-center gap-1.5 bg-muted/60 p-1 rounded-xl border border-border/40 self-start sm:self-auto">
          {[
            { label: "Last 7 Days", value: 7 },
            { label: "Last 30 Days", value: 30 },
            { label: "Last 90 Days", value: 90 },
          ].map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setDays(opt.value)}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-lg transition-all",
                days === opt.value
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Tokens */}
        <Card className="border bg-card">
          <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-medium text-muted-foreground">Total Tokens Used</CardTitle>
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <Sparkles className="size-4" />
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {isLoading ? (
              <Skeleton className="h-8 w-24 my-1" />
            ) : (
              <div className="text-2xl font-bold tracking-tight tabular-nums">
                {formatNumber(data?.summary?.total_tokens || 0)}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground mt-1">
              Across {data?.summary?.total_requests || 0} AI operations
            </p>
          </CardContent>
        </Card>

        {/* Input Tokens */}
        <Card className="border bg-card">
          <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-medium text-muted-foreground">Input (Prompt) Tokens</CardTitle>
            <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500">
              <Layers className="size-4" />
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {isLoading ? (
              <Skeleton className="h-8 w-24 my-1" />
            ) : (
              <div className="text-2xl font-bold tracking-tight tabular-nums">
                {formatNumber(data?.summary?.input_tokens || 0)}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground mt-1">
              {data?.summary?.total_tokens ? Math.round(((data.summary.input_tokens / data.summary.total_tokens) * 100)) : 0}% of all tokens
            </p>
          </CardContent>
        </Card>

        {/* Output Tokens */}
        <Card className="border bg-card">
          <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-medium text-muted-foreground">Output (Response) Tokens</CardTitle>
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500">
              <Zap className="size-4" />
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {isLoading ? (
              <Skeleton className="h-8 w-24 my-1" />
            ) : (
              <div className="text-2xl font-bold tracking-tight tabular-nums">
                {formatNumber(data?.summary?.output_tokens || 0)}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground mt-1">
              {data?.summary?.total_tokens ? Math.round(((data.summary.output_tokens / data.summary.total_tokens) * 100)) : 0}% of all tokens
            </p>
          </CardContent>
        </Card>

        {/* Estimated Cost */}
        <Card className="border bg-card">
          <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-medium text-muted-foreground">Estimated Cost (USD)</CardTitle>
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-500">
              <Coins className="size-4" />
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {isLoading ? (
              <Skeleton className="h-8 w-24 my-1" />
            ) : (
              <div className="text-2xl font-bold tracking-tight tabular-nums text-foreground">
                {formatCost(data?.summary?.total_cost_usd || 0)}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground mt-1">
              Billed directly by {data?.active_provider === "google" ? "Google Cloud" : "Provider"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Grid: Timeseries Chart & Feature Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Usage Chart (2 Cols) */}
        <Card className="lg:col-span-2 border bg-card">
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Activity className="size-4 text-primary" />
                  Daily Token Consumption
                </CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Volume of prompt and completion tokens processed per day
                </CardDescription>
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full bg-primary" /> Input
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full bg-emerald-500" /> Output
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-5 pt-2">
            {isLoading ? (
              <div className="h-48 flex items-center justify-center">
                <Skeleton className="h-36 w-full" />
              </div>
            ) : !data?.timeseries?.length ? (
              <div className="h-48 flex flex-col items-center justify-center text-center p-6 border border-dashed rounded-xl">
                <Calendar className="size-8 text-muted-foreground/40 mb-2" />
                <p className="text-sm font-medium text-foreground">No token activity recorded yet</p>
                <p className="text-xs text-muted-foreground max-w-xs mt-1">
                  When you run video clipping, PeakCut Post Text, or live monitoring, your token usage will appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-3 pt-2">
                <div className="h-44 flex items-end gap-2 sm:gap-3 px-1 pt-6 border-b border-border/40">
                  {data.timeseries.map((pt) => {
                    const heightPercent = Math.max(8, Math.round((pt.total_tokens / maxDailyTokens) * 100));
                    const inputRatio = pt.total_tokens > 0 ? pt.input_tokens / pt.total_tokens : 0.8;
                    const inputHeightPercent = Math.round(heightPercent * inputRatio);
                    const outputHeightPercent = heightPercent - inputHeightPercent;

                    return (
                      <div key={pt.date} className="flex-1 flex flex-col items-center gap-1 group relative h-full justify-end">
                        {/* Tooltip on Hover */}
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-12 z-20 pointer-events-none bg-popover text-popover-foreground text-[10px] py-1 px-2 rounded shadow-md border whitespace-nowrap">
                          <p className="font-bold">{pt.date}</p>
                          <p>{formatNumber(pt.total_tokens)} tokens ({formatCost(pt.cost_usd)})</p>
                        </div>

                        {/* Stacked Bar */}
                        <div
                          style={{ height: `${heightPercent}%` }}
                          className="w-full max-w-[28px] rounded-t-sm flex flex-col justify-end overflow-hidden transition-all group-hover:brightness-110"
                        >
                          <div style={{ height: `${outputHeightPercent}%` }} className="bg-emerald-500 w-full" />
                          <div style={{ height: `${inputHeightPercent}%` }} className="bg-primary w-full" />
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Date Labels */}
                <div className="flex justify-between text-[10px] text-muted-foreground px-1 font-mono">
                  <span>{data.timeseries[0]?.date}</span>
                  {data.timeseries.length > 2 && (
                    <span>{data.timeseries[Math.floor(data.timeseries.length / 2)]?.date}</span>
                  )}
                  <span>{data.timeseries[data.timeseries.length - 1]?.date}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Feature Breakdown (1 Col) */}
        <Card className="border bg-card">
          <CardHeader className="p-5 pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="size-4 text-primary" />
              Usage by Feature
            </CardTitle>
            <CardDescription className="text-xs mt-0.5">
              Where your AI tokens are being spent
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-2">
            {isLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : !data?.by_feature?.length ? (
              <p className="text-xs text-muted-foreground py-6 text-center">No feature usage recorded yet.</p>
            ) : (
              <div className="space-y-4">
                {data.by_feature.map((feat) => {
                  const total = data.summary?.total_tokens || 1;
                  const percentage = Math.round((feat.tokens / total) * 100);

                  return (
                    <div key={feat.feature || "unknown"} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-foreground">
                          {formatFeatureName(feat.feature || "")}
                        </span>
                        <span className="text-muted-foreground tabular-nums">
                          {formatNumber(feat.tokens)} ({percentage}%)
                        </span>
                      </div>
                      <Progress value={percentage} className="h-2" />
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                        <span>{feat.requests} calls</span>
                        <span>{formatCost(feat.cost_usd)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent AI Invocations Table */}
      <Card className="border bg-card overflow-hidden">
        <CardHeader className="p-5 pb-3 border-b">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Clock className="size-4 text-primary" />
                Recent AI Invocations
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Detailed audit log of real-time completions and token accounting
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-xs font-mono">
              Last {data?.recent_events?.length || 0} events
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5 space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : !data?.recent_events?.length ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No recent AI invocations found. Run a video clipping generation or live stream monitor to record activity.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-muted/50 text-muted-foreground border-b text-[11px] uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="py-2.5 px-4">Operation</th>
                    <th className="py-2.5 px-4">Model</th>
                    <th className="py-2.5 px-4 text-right">Prompt Tokens</th>
                    <th className="py-2.5 px-4 text-right">Completion</th>
                    <th className="py-2.5 px-4 text-right">Total Tokens</th>
                    <th className="py-2.5 px-4 text-right">Est. Cost</th>
                    <th className="py-2.5 px-4 text-right">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {data.recent_events.map((evt) => (
                    <tr key={evt.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-2.5 px-4">
                        <Badge variant="outline" className={cn("text-[10px] font-semibold", featureBadgeColor(evt.feature))}>
                          {formatFeatureName(evt.feature)}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-4 font-mono text-[11px] text-foreground">
                        {evt.model}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-muted-foreground">
                        {formatNumber(evt.input_tokens)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-muted-foreground">
                        {formatNumber(evt.output_tokens)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-semibold text-foreground">
                        {formatNumber(evt.total_tokens)}
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-mono text-emerald-500 font-semibold">
                        {formatCost(evt.cost_usd)}
                      </td>
                      <td className="py-2.5 px-4 text-right text-muted-foreground whitespace-nowrap">
                        {evt.created_at ? new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
