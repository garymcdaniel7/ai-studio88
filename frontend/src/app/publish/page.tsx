"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Calendar, Plus, ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { getPublishingPosts } from "@/lib/api";
import { useToast } from "@/components/toast";

interface Post {
  id: string;
  title?: string;
  platform?: string;
  scheduled_for?: string;
  status?: string;
}

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfWeek(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function PublishPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [scheduleTitle, setScheduleTitle] = useState("");
  const [schedulePlatform, setSchedulePlatform] = useState("Instagram");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleContent, setScheduleContent] = useState("");
  const [scheduleSubmitting, setScheduleSubmitting] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    loadPosts();
  }, []);

  function loadPosts() {
    setLoading(true);
    getPublishingPosts()
      .then((data) => setPosts(Array.isArray(data) ? data as unknown as Post[] : []))
      .catch(() => setPosts([]))
      .finally(() => setLoading(false));
  }

  async function handleScheduleSubmit() {
    if (!scheduleTitle.trim() || !scheduleDate) return;
    setScheduleSubmitting(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/publishing/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: scheduleTitle,
          platform: schedulePlatform,
          scheduled_for: scheduleDate,
          content: scheduleContent,
          status: "scheduled",
        }),
      });
      if (!resp.ok) throw new Error("Failed to schedule");
      show("Post scheduled successfully!", "success");
      setShowScheduleForm(false);
      setScheduleTitle("");
      setSchedulePlatform("Instagram");
      setScheduleDate("");
      setScheduleContent("");
      loadPosts();
    } catch {
      show("Failed to schedule post. Is the backend running?", "error");
    } finally {
      setScheduleSubmitting(false);
    }
  }

  function prevMonth() {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
  }

  function nextMonth() {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
  }

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfWeek(year, month);
  const today = now.getDate();
  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth();

  // Build map of day -> posts
  const postsByDay: Record<number, Post[]> = {};
  posts.forEach((post) => {
    if (!post.scheduled_for) return;
    const d = new Date(post.scheduled_for);
    if (d.getFullYear() === year && d.getMonth() === month) {
      const day = d.getDate();
      if (!postsByDay[day]) postsByDay[day] = [];
      postsByDay[day].push(post);
    }
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Publish</h1>
          <p className="text-sm text-gray-500">
            Social publishing, scheduling, campaigns, and content calendar.
          </p>
        </div>
        <button
          onClick={() => setShowScheduleForm(!showScheduleForm)}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
        >
          <Plus className="h-4 w-4" /> Schedule Post
        </button>
      </div>

      {/* Connected Platforms */}
      <ConnectedPlatforms />

      {/* Schedule Form */}
      {showScheduleForm && (
        <div className="rounded-xl border border-purple-500/30 bg-[#12122a] p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Schedule a Post</h3>
            <button onClick={() => setShowScheduleForm(false)} className="text-gray-400 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-3">
            <input
              value={scheduleTitle}
              onChange={(e) => setScheduleTitle(e.target.value)}
              placeholder="Post title"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
            />
            <select
              value={schedulePlatform}
              onChange={(e) => setSchedulePlatform(e.target.value)}
              className="w-full rounded-lg border border-white/[0.08] bg-[#12122a] px-4 py-2 text-sm text-gray-300 outline-none"
            >
              <option value="Instagram">Instagram</option>
              <option value="TikTok">TikTok</option>
              <option value="YouTube">YouTube</option>
              <option value="Twitter/X">Twitter/X</option>
            </select>
            <input
              type="datetime-local"
              value={scheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 outline-none focus:border-purple-500/50 [color-scheme:dark]"
            />
            <textarea
              value={scheduleContent}
              onChange={(e) => setScheduleContent(e.target.value)}
              placeholder="Post content / caption..."
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none resize-none"
              rows={3}
            />
            <div className="flex gap-2">
              <button
                onClick={handleScheduleSubmit}
                disabled={scheduleSubmitting || !scheduleTitle.trim() || !scheduleDate}
                className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
              >
                {scheduleSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {scheduleSubmitting ? "Scheduling..." : "Schedule"}
              </button>
              <button
                onClick={() => setShowScheduleForm(false)}
                className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-400 hover:bg-white/[0.04]"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Calendar */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        {/* Month Navigation */}
        <div className="flex items-center justify-between mb-4">
          <button onClick={prevMonth} className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-white/[0.05]">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <h2 className="text-lg font-semibold text-white">
            {MONTH_NAMES[month]} {year}
          </h2>
          <button onClick={nextMonth} className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-white/[0.05]">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
          </div>
        ) : (
          <>
            {/* Day Headers */}
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAY_NAMES.map((day) => (
                <div key={day} className="text-center text-xs font-medium text-gray-500 py-2">
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar Grid */}
            <div className="grid grid-cols-7 gap-1">
              {/* Empty cells for offset */}
              {Array.from({ length: firstDay }).map((_, i) => (
                <div key={`empty-${i}`} className="min-h-[80px] rounded-lg bg-white/[0.01]" />
              ))}
              {/* Day cells */}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const day = i + 1;
                const isToday = isCurrentMonth && day === today;
                const dayPosts = postsByDay[day] || [];
                return (
                  <div
                    key={day}
                    className={`min-h-[80px] rounded-lg border p-2 ${
                      isToday
                        ? "border-purple-500/50 bg-purple-600/10"
                        : "border-white/[0.04] bg-white/[0.02] hover:bg-white/[0.04]"
                    }`}
                  >
                    <p className={`text-xs font-medium ${isToday ? "text-purple-300" : "text-gray-400"}`}>
                      {day}
                    </p>
                    {dayPosts.length > 0 && (
                      <div className="mt-1 space-y-1">
                        {dayPosts.slice(0, 2).map((post, idx) => (
                          <div
                            key={post.id || idx}
                            className="rounded bg-purple-600/20 px-1.5 py-0.5 text-[10px] text-purple-300 truncate"
                          >
                            {post.title || post.platform || "Post"}
                          </div>
                        ))}
                        {dayPosts.length > 2 && (
                          <p className="text-[10px] text-gray-500">+{dayPosts.length - 2} more</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* Scheduled Posts List */}
      {posts.filter((p) => p.scheduled_for).length > 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <h3 className="text-sm font-semibold text-white mb-3">Upcoming Scheduled Posts</h3>
          <div className="space-y-2">
            {posts
              .filter((p) => p.scheduled_for)
              .sort((a, b) => new Date(a.scheduled_for!).getTime() - new Date(b.scheduled_for!).getTime())
              .slice(0, 10)
              .map((post, idx) => (
                <div key={post.id || idx} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3 group">
                  <Calendar className="h-4 w-4 text-purple-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{post.title || "Untitled Post"}</p>
                    <p className="text-xs text-gray-500">{post.platform || "—"}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(post.scheduled_for!).toLocaleDateString()}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    post.status === "published" ? "bg-green-500/20 text-green-400" : "bg-amber-500/20 text-amber-400"
                  }`}>
                    {post.status || "scheduled"}
                  </span>
                  <button
                    onClick={async () => {
                      if (!confirm("Delete this scheduled post?")) return;
                      try {
                        await fetch(`${API_BASE}/api/v1/publishing/posts/${post.id}`, { method: "DELETE" });
                        setPosts((prev) => prev.filter((p) => p.id !== post.id));
                        show("Post deleted", "success");
                      } catch { show("Failed to delete", "error"); }
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-gray-600 hover:text-red-400 transition-all"
                    title="Delete post"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Connected Platforms — OAuth connect/disconnect
// ---------------------------------------------------------------------------

function ConnectedPlatforms() {
  const [platforms, setPlatforms] = useState<{platform: string; connected: boolean; configured: boolean; display_name: string; icon: string}[]>([]);
  const [connecting, setConnecting] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/publishing/oauth/platforms`)
      .then((r) => r.json())
      .then((data) => {
        if (data?.platforms) setPlatforms(data.platforms);
      })
      .catch(() => {});

    // Listen for OAuth popup callback
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === "oauth_callback") {
        setConnecting(null);
        // Refresh platforms
        fetch(`${API_BASE}/api/v1/publishing/oauth/platforms`)
          .then((r) => r.json())
          .then((data) => { if (data?.platforms) setPlatforms(data.platforms); })
          .catch(() => {});
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  async function handleConnect(platform: string) {
    setConnecting(platform);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/publishing/oauth/${platform}/authorize`);
      const data = await resp.json();
      if (data.authorize_url) {
        // Open OAuth popup
        window.open(data.authorize_url, `${platform}_oauth`, "width=600,height=700,popup=yes");
      } else {
        setConnecting(null);
      }
    } catch {
      setConnecting(null);
    }
  }

  async function handleDisconnect(platform: string) {
    await fetch(`${API_BASE}/api/v1/publishing/oauth/connections/${platform}`, { method: "DELETE" });
    setPlatforms((prev) => prev.map((p) => p.platform === platform ? { ...p, connected: false } : p));
  }

  if (platforms.length === 0) return null;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
      <h3 className="text-sm font-semibold text-white mb-3">Connected Platforms</h3>
      <div className="grid grid-cols-4 gap-3">
        {platforms.map((p) => (
          <div key={p.platform} className={`rounded-xl border p-4 text-center ${
            p.connected ? "border-green-500/30 bg-green-500/5" : "border-white/[0.06] bg-white/[0.02]"
          }`}>
            <span className="text-2xl">{p.icon}</span>
            <p className="text-xs font-medium text-white mt-2">{p.display_name}</p>
            {p.connected ? (
              <div className="mt-2 space-y-1">
                <span className="inline-flex items-center gap-1 text-[10px] text-green-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400" /> Connected
                </span>
                <button
                  onClick={() => handleDisconnect(p.platform)}
                  className="block w-full text-[10px] text-gray-500 hover:text-red-400 transition-colors"
                >
                  Disconnect
                </button>
              </div>
            ) : p.configured ? (
              <button
                onClick={() => handleConnect(p.platform)}
                disabled={connecting === p.platform}
                className="mt-2 rounded-lg bg-purple-600 px-3 py-1 text-[10px] font-medium text-white hover:bg-purple-700 disabled:opacity-50"
              >
                {connecting === p.platform ? "Connecting..." : "Connect"}
              </button>
            ) : (
              <p className="mt-2 text-[10px] text-gray-600">Not configured</p>
            )}
          </div>
        ))}
      </div>
      <p className="text-[10px] text-gray-600 mt-3">
        Configure API keys in Admin → API Keys to enable platforms.
      </p>
    </div>
  );
}
