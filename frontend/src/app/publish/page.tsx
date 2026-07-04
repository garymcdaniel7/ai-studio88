"use client";

import { useEffect, useState } from "react";
import { Calendar, Plus, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { getPublishingPosts } from "@/lib/api";

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

  useEffect(() => {
    getPublishingPosts()
      .then((data) => setPosts(Array.isArray(data) ? data : []))
      .catch(() => setPosts([]))
      .finally(() => setLoading(false));
  }, []);

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
          onClick={() => alert("Schedule Post will be available once social accounts are connected. Configure in Admin → Integrations.")}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
        >
          <Plus className="h-4 w-4" /> Schedule Post
        </button>
      </div>

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
                <div key={post.id || idx} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
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
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
