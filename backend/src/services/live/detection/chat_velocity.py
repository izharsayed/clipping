"""Real-time chat velocity and emote burst tracking for live streams."""

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

TWITCH_IRC_HOST = "irc.chat.twitch.tv"
TWITCH_IRC_PORT = 6667

# Common viral and high-engagement Twitch / Kick chat emotes and keywords
LAUGHTER_EMOTES: Set[str] = {
    "kekw", "lul", "lulw", "omegalul", "icant", "lmao", "lol", "haha", "xd",
    "dead", "ahah", "hahaha", "hahahaha",
}

HYPE_EMOTES: Set[str] = {
    "pog", "poggers", "pogu", "w", "huge", "letsgo", "insane", "clutch", "goat",
    "holy", "clipit", "clip it", "sheesh", "fire", "omg", "w streamer",
}

SHOCK_EMOTES: Set[str] = {
    "monkas", "wtf", "bro", "no way", "noway", "what", "rip", "skull", "caught",
    "ayooo", "ayoo", "sus", "aintnoway", "aint no way",
}

ALL_VIRAL_EMOTES: Set[str] = LAUGHTER_EMOTES | HYPE_EMOTES | SHOCK_EMOTES


@dataclass
class ChatVelocityResult:
    """Current velocity and emote surge metrics."""

    messages_per_second: float
    laughter_ratio: float  # Fraction of recent messages containing laugh emotes (0.0 to 1.0)
    hype_ratio: float      # Fraction of recent messages containing hype/shock emotes (0.0 to 1.0)
    baseline_velocity: float
    spike_ratio: float     # Ratio of current velocity to rolling baseline
    is_chat_spike: bool
    top_emotes: List[str] = field(default_factory=list)


class ChatVelocityTracker:
    """
    Tracks incoming chat messages in a rolling time window to compute
    chat velocity (messages/sec), emote frequencies, and excitement surges.
    """

    def __init__(
        self,
        window_seconds: float = 8.0,
        spike_multiplier: float = 2.4,
        alpha: float = 0.90,  # Moving average smoothing for baseline
        min_msg_rate_threshold: float = 1.0,  # Minimum msgs/sec to consider a spike
    ):
        self.window_seconds = window_seconds
        self.spike_multiplier = spike_multiplier
        self.alpha = alpha
        self.min_msg_rate_threshold = min_msg_rate_threshold

        # Timestamps of incoming messages: deque of (timestamp, is_laughter, is_hype, matched_emotes)
        self._history: Deque[Tuple[float, bool, bool, List[str]]] = deque()
        self.baseline_velocity: Optional[float] = None
        self._last_baseline_update: float = time.time()

    def record_message(self, text: str, timestamp: Optional[float] = None) -> None:
        """Record an incoming chat message text and extract emotes."""
        now = timestamp if timestamp is not None else time.time()
        words = re.findall(r"[\w]+|[?!]+", text.lower())

        is_laughter = any(w in LAUGHTER_EMOTES for w in words)
        is_hype = any(w in HYPE_EMOTES or w in SHOCK_EMOTES for w in words)
        matched = [w for w in words if w in ALL_VIRAL_EMOTES]

        self._history.append((now, is_laughter, is_hype, matched))
        self._prune(now)

    def _prune(self, now: float) -> None:
        """Evict messages older than the sliding window."""
        cutoff = now - self.window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def get_current_velocity(self, timestamp: Optional[float] = None) -> ChatVelocityResult:
        """Calculate current messages per second, emote ratio, and spike metrics."""
        now = timestamp if timestamp is not None else time.time()
        self._prune(now)

        total_msgs = len(self._history)
        mps = round(total_msgs / max(self.window_seconds, 1.0), 2)

        laughter_count = sum(1 for _, is_l, _, _ in self._history if is_l)
        hype_count = sum(1 for _, _, is_h, _ in self._history if is_h)

        laughter_ratio = round(laughter_count / max(total_msgs, 1), 2)
        hype_ratio = round(hype_count / max(total_msgs, 1), 2)

        # Count top matched emotes
        emote_counts: Dict[str, int] = {}
        for _, _, _, matched in self._history:
            for em in matched:
                emote_counts[em] = emote_counts.get(em, 0) + 1
        top_emotes = [em.upper() for em, _ in sorted(emote_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

        # Baseline velocity update
        if self.baseline_velocity is None:
            self.baseline_velocity = max(mps, 0.5)
            spike_ratio = 1.0
            is_spike = False
        else:
            effective_base = max(self.baseline_velocity, 0.5)
            spike_ratio = round(mps / effective_base, 2)
            is_spike = (
                spike_ratio >= self.spike_multiplier
                and mps >= self.min_msg_rate_threshold
            )

            # Update baseline if not currently spiking (every 2s)
            if not is_spike and (now - self._last_baseline_update) >= 2.0:
                self.baseline_velocity = round(
                    (self.alpha * self.baseline_velocity) + ((1.0 - self.alpha) * mps),
                    2,
                )
                self._last_baseline_update = now

        return ChatVelocityResult(
            messages_per_second=mps,
            laughter_ratio=laughter_ratio,
            hype_ratio=hype_ratio,
            baseline_velocity=self.baseline_velocity,
            spike_ratio=spike_ratio,
            is_chat_spike=is_spike,
            top_emotes=top_emotes,
        )


class TwitchChatMonitor:
    """
    Connects to Twitch IRC anonymously and feeds public messages
    into a ChatVelocityTracker in real-time.
    """

    def __init__(self, channel_identifier: str, tracker: Optional[ChatVelocityTracker] = None):
        self.channel_identifier = channel_identifier.lstrip("#").lower()
        self.tracker = tracker or ChatVelocityTracker()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def start(self) -> None:
        """Start anonymous IRC connection and listener task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("Started Twitch chat monitor for channel #%s", self.channel_identifier)

    async def stop(self) -> None:
        """Stop IRC listener and close socket."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        logger.info("Stopped Twitch chat monitor for channel #%s", self.channel_identifier)

    async def _listen_loop(self) -> None:
        """Continuous connection and reading loop with reconnection."""
        while self._running:
            try:
                logger.debug("Connecting to Twitch IRC %s:%d...", TWITCH_IRC_HOST, TWITCH_IRC_PORT)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(TWITCH_IRC_HOST, TWITCH_IRC_PORT),
                    timeout=8.0,
                )

                # Anonymous login commands
                anon_nick = f"justinfan{int(time.time() * 1000) % 89999 + 10000}"
                auth_cmds = (
                    f"PASS SCHMOOPIE\r\n"
                    f"NICK {anon_nick}\r\n"
                    f"JOIN #{self.channel_identifier}\r\n"
                )
                self._writer.write(auth_cmds.encode("utf-8"))
                await self._writer.drain()

                logger.info("Joined Twitch chat #%s as %s", self.channel_identifier, anon_nick)

                while self._running and self._reader:
                    line = await self._reader.readline()
                    if not line:
                        break  # Disconnected

                    raw_text = line.decode("utf-8", errors="replace").strip()

                    # Handle heartbeat
                    if raw_text.startswith("PING"):
                        pong_resp = raw_text.replace("PING", "PONG") + "\r\n"
                        self._writer.write(pong_resp.encode("utf-8"))
                        await self._writer.drain()
                        continue

                    # Parse PRIVMSG
                    # Format: :username!username@username.tmi.twitch.tv PRIVMSG #channel :message text
                    if "PRIVMSG" in raw_text:
                        parts = raw_text.split("PRIVMSG", 1)
                        if len(parts) == 2 and ":" in parts[1]:
                            msg_text = parts[1].split(":", 1)[1]
                            self.tracker.record_message(msg_text)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Twitch IRC connection notice for #%s: %s", self.channel_identifier, exc)

            if self._running:
                await asyncio.sleep(4.0)  # Reconnection cooldown
