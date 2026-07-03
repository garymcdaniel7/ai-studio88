# AI Studio — Publishing Engine

> Priority 8. Social media publishing, analytics, and content repurposing.

---

## Overview

Full publishing lifecycle: asset → platform package → approval → schedule → publish → analytics → learning.

```
Asset → Package → Approve → Schedule → Publish → Analytics → Learn
```

---

## Supported Platforms (13)

instagram, tiktok, youtube, youtube_shorts, facebook, threads,
pinterest, linkedin, x, website, blog, email, podcast

---

## Pipeline

```
1. Create publishing post (link asset, platform, caption, hashtags)
2. Platform packaging (validate requirements)
3. Approval workflow (approve/reject)
4. Schedule (set date/time)
5. Publish (via SocialProvider)
6. Track analytics (views, likes, engagement)
7. Learning feedback (feed into Creative DNA, recommendations)
```

---

## API Endpoints (15+)

| Method | Path | Description |
|---|---|---|
| GET | `/publishing/posts` | List posts |
| POST | `/publishing/posts` | Create draft post |
| GET | `/publishing/posts/{id}` | Get post |
| POST | `/publishing/posts/{id}/approve` | Approve for publishing |
| POST | `/publishing/posts/{id}/reject` | Reject with reason |
| POST | `/publishing/posts/{id}/schedule` | Schedule for time |
| POST | `/publishing/posts/{id}/publish` | Publish now (simulated) |
| GET | `/publishing/analytics` | List analytics snapshots |
| POST | `/publishing/analytics/simulate` | Simulate analytics fetch |
| GET | `/publishing/analytics/summary` | Aggregate summary |
| GET | `/publishing/platforms` | All platforms with requirements |
| POST | `/publishing/package` | Create platform package |
| GET | `/publishing/repurpose/formats` | List repurpose formats |
| POST | `/publishing/repurpose` | Create repurpose plan |
| GET | `/publishing/calendar` | Calendar view |
| GET | `/publishing/providers/health` | Provider health |

---

## Platform Requirements

Each platform has validated requirements:
- Aspect ratios, max duration, caption length
- Hashtag limit, file size, supported formats
- Recommended posting times

---

## Approval Workflow

| Status | Flow |
|---|---|
| pending | → approve / reject |
| approved | → schedule / publish now |
| rejected | → revise → resubmit |
| scheduled | → auto-publish at time |
| published | → track analytics |

---

## Analytics

Tracked per post: views, likes, comments, shares, saves, reach,
impressions, watch_time, completion_rate, CTR, follower_delta, revenue

---

## Repurposing (14 formats)

One asset → instagram_reel, tiktok, youtube_short, trailer, story,
carousel, thumbnail, wallpaper, newsletter, behind_the_scenes,
podcast_clip, gif, teaser, quote_graphic

---

## Database Tables (4 new)

`publishing_accounts`, `publishing_posts`, `analytics_snapshots`, `platform_packages`

See `docs/sql/012_publishing_engine.sql`.

---

## Provider Interface

```python
class SocialProvider(ABC):
    def health(self) -> dict
    def capabilities(self) -> dict
    def requirements(self) -> PlatformRequirements
    def publish(self, post) -> PublishResult
    def fetch_analytics(self, post_id) -> dict
    def validate_media(self, asset) -> (bool, issues)
```

Future providers: InstagramProvider, TikTokProvider, YouTubeProvider, etc.
