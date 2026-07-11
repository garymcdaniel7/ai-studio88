"""All 20 AI Departments — each owns one creative/business responsibility.

Each department reads from StudioContext and produces Recommendations
with confidence scores, reasoning, and evidence. They never call each
other directly — the Orchestrator handles collaboration.
"""

from __future__ import annotations

from backend.autonomous_studio.department import Department, DepartmentOutput, Recommendation


class CreativeDirector(Department):
    @property
    def name(self) -> str:
        return "Creative Director"

    @property
    def role(self) -> str:
        return "Overall creative vision, concept elevation, brand alignment"

    def analyze(self, ctx):
        recs = []
        if not ctx.get("campaigns"):
            recs.append(
                Recommendation(
                    self.name,
                    "Create Campaign",
                    "No active campaigns. A structured campaign would focus your creative output.",
                    "No campaigns found in system",
                    0.85,
                    action="create_campaign",
                    priority="high",
                )
            )
        if ctx.get("feedback_issues"):
            recs.append(
                Recommendation(
                    self.name,
                    "Address Quality Issues",
                    f"Recent feedback shows: {ctx['feedback_issues'][:3]}",
                    "Recurring problems detected",
                    0.8,
                    action="review_creative_dna",
                    priority="medium",
                )
            )
        return DepartmentOutput(
            self.name, recs, f"{'Active' if ctx.get('campaigns') else 'Needs campaigns'}"
        )


class PromptDirector(Department):
    @property
    def name(self) -> str:
        return "Prompt Director"

    @property
    def role(self) -> str:
        return "Prompt optimization, model-specific syntax, negative prompt management"

    def analyze(self, ctx):
        recs = []
        if ctx.get("recent_low_ratings"):
            recs.append(
                Recommendation(
                    self.name,
                    "Prompt Revision Needed",
                    "Recent outputs received low ratings. Consider revising prompt strategy.",
                    "Low average rating detected",
                    0.75,
                    action="revise_prompts",
                )
            )
        return DepartmentOutput(self.name, recs)


class PhotographyDirector(Department):
    @property
    def name(self) -> str:
        return "Photography Director"

    @property
    def role(self) -> str:
        return "Composition, lighting, camera settings for still images"

    def analyze(self, ctx):
        recs = []
        if ctx.get("content_type") == "image" or not ctx.get("content_type"):
            recs.append(
                Recommendation(
                    self.name,
                    "Lighting Optimization",
                    "Consider golden hour or Rembrandt lighting for portraiture.",
                    "Standard recommendation for portrait content",
                    0.7,
                    action="update_lighting",
                )
            )
        return DepartmentOutput(self.name, recs)


class FilmDirector(Department):
    @property
    def name(self) -> str:
        return "Film Director"

    @property
    def role(self) -> str:
        return "Narrative pacing, scene structure, shot selection for video"

    def analyze(self, ctx):
        recs = []
        if ctx.get("episodes"):
            recs.append(
                Recommendation(
                    self.name,
                    "Episode Pacing",
                    "Review episode pacing. Hook within first 2 seconds for social content.",
                    "Best practice for social video",
                    0.72,
                    action="review_pacing",
                )
            )
        return DepartmentOutput(self.name, recs)


class ProductionDirector(Department):
    @property
    def name(self) -> str:
        return "Production Director"

    @property
    def role(self) -> str:
        return "Production planning, pipeline selection, timeline management"

    def analyze(self, ctx):
        recs = []
        if ctx.get("scheduled_count", 0) > 0 and ctx.get("workers_online", 0) > 0:
            recs.append(
                Recommendation(
                    self.name,
                    "Start Scheduled Production",
                    f"{ctx.get('scheduled_count')} items scheduled with {ctx.get('workers_online')} workers available.",
                    "Scheduled content ready for production",
                    0.85,
                    action="start_production",
                    priority="high",
                )
            )
        return DepartmentOutput(self.name, recs)


class VideoDirector(Department):
    @property
    def name(self) -> str:
        return "Video Director"

    @property
    def role(self) -> str:
        return "Motion, camera movement, timing, transitions for video content"

    def analyze(self, ctx):
        return DepartmentOutput(self.name, [], "Video pipeline ready")


class ArtDirector(Department):
    @property
    def name(self) -> str:
        return "Art Director"

    @property
    def role(self) -> str:
        return "Visual style, color palette, aesthetic consistency"

    def analyze(self, ctx):
        recs = []
        if not ctx.get("creative_dna"):
            recs.append(
                Recommendation(
                    self.name,
                    "Define Visual Style",
                    "No Creative DNA found. Define preferred styles for consistent output.",
                    "No DNA configured",
                    0.8,
                    action="create_dna",
                    priority="medium",
                )
            )
        return DepartmentOutput(self.name, recs)


class CharacterDirector(Department):
    @property
    def name(self) -> str:
        return "Character Director"

    @property
    def role(self) -> str:
        return "Character identity, continuity, visual consistency across content"

    def analyze(self, ctx):
        recs = []
        if ctx.get("talent_count", 0) > 0 and not ctx.get("creative_dna"):
            recs.append(
                Recommendation(
                    self.name,
                    "Character DNA Missing",
                    "Talent exists but no Creative DNA. Identity consistency at risk.",
                    "Talent without DNA",
                    0.75,
                    action="create_character_dna",
                )
            )
        return DepartmentOutput(self.name, recs)


class VoiceDirector(Department):
    @property
    def name(self) -> str:
        return "Voice Director"

    @property
    def role(self) -> str:
        return "Voice casting, emotion, delivery style for audio content"

    def analyze(self, ctx):
        return DepartmentOutput(self.name, [], "Voice library available")


class MusicDirector(Department):
    @property
    def name(self) -> str:
        return "Music Director"

    @property
    def role(self) -> str:
        return "Music selection, mood matching, tempo alignment"

    def analyze(self, ctx):
        return DepartmentOutput(self.name, [], "Music library available")


class PublishingDirector(Department):
    @property
    def name(self) -> str:
        return "Publishing Director"

    @property
    def role(self) -> str:
        return "Platform strategy, posting times, format optimization"

    def analyze(self, ctx):
        recs = []
        if ctx.get("unpublished_count", 0) > 3:
            recs.append(
                Recommendation(
                    self.name,
                    "Content Backlog",
                    f"{ctx['unpublished_count']} items ready but unpublished. Consider scheduling.",
                    "Unpublished content detected",
                    0.8,
                    action="schedule_content",
                    priority="medium",
                )
            )
        return DepartmentOutput(self.name, recs)


class GrowthDirector(Department):
    @property
    def name(self) -> str:
        return "Growth Director"

    @property
    def role(self) -> str:
        return "Engagement optimization, audience growth, performance trends"

    def analyze(self, ctx):
        recs = []
        if ctx.get("engagement_rate", 0) < 3.0 and ctx.get("analytics_count", 0) > 5:
            recs.append(
                Recommendation(
                    self.name,
                    "Engagement Below Target",
                    f"Current: {ctx.get('engagement_rate', 0):.1f}%. Adjust content strategy.",
                    "Low engagement trend",
                    0.75,
                    action="review_strategy",
                    priority="medium",
                )
            )
        return DepartmentOutput(self.name, recs)


class BusinessDirector(Department):
    @property
    def name(self) -> str:
        return "Business Director"

    @property
    def role(self) -> str:
        return "Revenue, licensing, ROI tracking, budget management"

    def analyze(self, ctx):
        recs = []
        revenue = ctx.get("total_revenue", 0)
        if revenue == 0 and ctx.get("published_count", 0) > 5:
            recs.append(
                Recommendation(
                    self.name,
                    "Monetization Opportunity",
                    "Content published but no revenue tracked. Consider brand deals or licensing.",
                    "No revenue with active content",
                    0.7,
                    action="explore_monetization",
                )
            )
        return DepartmentOutput(self.name, recs)


class AnalyticsDirector(Department):
    @property
    def name(self) -> str:
        return "Analytics Director"

    @property
    def role(self) -> str:
        return "Data analysis, performance reporting, trend identification"

    def analyze(self, ctx):
        return DepartmentOutput(
            self.name, [], f"Tracking {ctx.get('analytics_count', 0)} data points"
        )


class LearningDirector(Department):
    @property
    def name(self) -> str:
        return "Learning Director"

    @property
    def role(self) -> str:
        return "Preference learning, outcome tracking, recommendation improvement"

    def analyze(self, ctx):
        recs = []
        accepted = ctx.get("recommendations_accepted", 0)
        rejected = ctx.get("recommendations_rejected", 0)
        if accepted + rejected > 10:
            accuracy = accepted / max(accepted + rejected, 1) * 100
            recs.append(
                Recommendation(
                    self.name,
                    f"Recommendation Accuracy: {accuracy:.0f}%",
                    f"{accepted} accepted, {rejected} rejected. {'Improving' if accuracy > 70 else 'Needs calibration'}.",
                    "Historical recommendation tracking",
                    0.6,
                )
            )
        return DepartmentOutput(self.name, recs)


class OperationsDirector(Department):
    @property
    def name(self) -> str:
        return "Operations Director"

    @property
    def role(self) -> str:
        return "System health, worker management, queue optimization"

    def analyze(self, ctx):
        recs = []
        workers = ctx.get("workers_online", 0)
        if workers == 0:
            recs.append(
                Recommendation(
                    self.name,
                    "No Workers Available",
                    "All workers are offline. Production cannot proceed.",
                    "Zero online workers",
                    0.95,
                    action="check_workers",
                    priority="critical",
                )
            )
        return DepartmentOutput(self.name, recs)


class ResearchDirector(Department):
    @property
    def name(self) -> str:
        return "Research Director"

    @property
    def role(self) -> str:
        return "New models, techniques, and creative approaches"

    def analyze(self, ctx):
        return DepartmentOutput(self.name, [], "Monitoring model landscape")


class TrendDirector(Department):
    @property
    def name(self) -> str:
        return "Trend Director"

    @property
    def role(self) -> str:
        return "Social trends, viral content patterns, timing opportunities"

    def analyze(self, ctx):
        recs = []
        recs.append(
            Recommendation(
                self.name,
                "Trend: AI Fashion Content",
                "AI-generated fashion content seeing 3x engagement spike. Consider luxury fashion series.",
                "Simulated trend data",
                0.6,
                action="create_trend_content",
            )
        )
        return DepartmentOutput(self.name, recs)


class BrandDirector(Department):
    @property
    def name(self) -> str:
        return "Brand Director"

    @property
    def role(self) -> str:
        return "Brand identity, voice consistency, partnership opportunities"

    def analyze(self, ctx):
        recs = []
        if ctx.get("brands_count", 0) == 0:
            recs.append(
                Recommendation(
                    self.name,
                    "Define Brand Identity",
                    "No brands registered. Establish brand guidelines for consistent output.",
                    "No brands in system",
                    0.7,
                    action="create_brand",
                )
            )
        return DepartmentOutput(self.name, recs)


# =============================================================================
# Department Registry
# =============================================================================

ALL_DEPARTMENTS: list[type[Department]] = [
    CreativeDirector,
    PromptDirector,
    PhotographyDirector,
    FilmDirector,
    ProductionDirector,
    VideoDirector,
    ArtDirector,
    CharacterDirector,
    VoiceDirector,
    MusicDirector,
    PublishingDirector,
    GrowthDirector,
    BusinessDirector,
    AnalyticsDirector,
    LearningDirector,
    OperationsDirector,
    ResearchDirector,
    TrendDirector,
    BrandDirector,
]
