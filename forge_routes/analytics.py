"""Analytics dashboards with unchanged T-106 metrics and scope."""

from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, jsonify


def create_analytics_blueprint(*, require_login, daily_series, cumulative,
                               profile_view_model, network_request_model,
                               post_model, like_model, comment_model, user_model,
                               skill_search_model, connection_npc_model,
                               opportunity_model, business_listing_model,
                               application_model, approval_queue_item_model,
                               alumni_verification_model, event_model):
    """Use existing models and policies without importing the app entrypoint."""
    blueprint = Blueprint("analytics", __name__)

    @blueprint.get("/api/analytics/student")
    def student_analytics():
        user, err = require_login()
        if err:
            return err
        views = profile_view_model.query.filter_by(viewed_user_id=user.id).all()
        accepted = network_request_model.query.filter_by(status="accepted") \
            .order_by(network_request_model.created_at).all()
        my_posts = post_model.query.filter(post_model.author_name == user.name,
                                          post_model.removed.is_(False)).all()
        likes_received = sum(p.base_likes + like_model.query.filter_by(post_id=p.id).count()
                             for p in my_posts)
        comments_received = sum(comment_model.query.filter_by(post_id=p.id).count()
                                for p in my_posts)
        peers = user_model.query.filter(user_model.role == user.role,
                                        user_model.programme == user.programme,
                                        user_model.id != user.id).all()
        programme_avg = int(sum(p.completion for p in peers) / len(peers)) if peers else None
        mine = {s.strip().lower() for s in (user.skills or "").split(",") if s.strip()}
        counts = defaultdict(int)
        for search in skill_search_model.query.all():
            if search.skill.lower() in mine:
                counts[search.skill] += 1
        top = sorted(({"skill": k, "count": v} for k, v in counts.items()),
                     key=lambda x: -x["count"])[:5]
        return jsonify({
            "profileViews": {"total": len(views),
                             "series": daily_series([v.created_at for v in views])},
            "connections": {"total": len(accepted) + connection_npc_model.query.count(),
                            "series": cumulative(daily_series([r.created_at for r in accepted]))},
            "engagement": {"posts": len(my_posts), "likes": likes_received,
                           "comments": comments_received},
            "peerComparison": {"me": user.completion, "programmeAvg": programme_avg,
                               "programme": user.programme},
            "topSearchedSkills": top,
        })


    @blueprint.get("/api/analytics/business")
    def business_analytics():
        user, err = require_login()
        if err:
            return err
        if user.role not in ("business", "admin"):
            return jsonify({"error": "business or admin only"}), 403
        # Businesses receive only their own hiring funnel. Admins are authorized to
        # inspect this dashboard as the platform-wide hiring funnel, not as an
        # empty pseudo-business account.
        if user.role == "business":
            opps = opportunity_model.query.filter_by(owner_user_id=user.id).all()
            listings = business_listing_model.query.filter_by(owner_user_id=user.id).all()
            profile_views = profile_view_model.query.filter_by(viewed_user_id=user.id).count()
        else:
            opps = opportunity_model.query.all()
            listings = business_listing_model.query.all()
            profile_views = profile_view_model.query.count()
        pipeline, applicant_ids = [], []
        for opp in opps:
            apps = application_model.query.filter_by(opportunity_id=opp.id).all()
            pipeline.append({"title": opp.title, "applicants": len(apps), "status": "live"})
            applicant_ids.extend(a.user_id for a in apps)
        applicants = [u for u in (user_model.query.get(i) for i in applicant_ids) if u]
        skill_counts, by_programme, by_year = defaultdict(int), defaultdict(int), defaultdict(int)
        for a in applicants:
            for s in (a.skills or "").split(","):
                if s.strip():
                    skill_counts[s.strip()] += 1
            by_programme[a.programme or "Unspecified"] += 1
            by_year[a.year or "Unspecified"] += 1

        def dist(d):
            return sorted(({"label": k, "count": v} for k, v in d.items()),
                          key=lambda x: -x["count"])

        impressions = sum(l.impressions for l in listings)
        total_apps = len(applicant_ids)
        rate = f"{round(100 * total_apps / impressions)}%" if impressions else "—"
        return jsonify({
            "pipeline": pipeline,
            "engagement": {"impressions": impressions, "applications": total_apps, "rate": rate},
            "skillDistribution": dist(skill_counts),
            "demographics": {"byProgramme": dist(by_programme), "byYear": dist(by_year)},
            "reach": {"profileViews": profile_views,
                      "impressions": impressions},
        })


    @blueprint.get("/api/analytics/admin")
    def admin_analytics():
        user, err = require_login()
        if err:
            return err
        if user.role != "admin":
            return jsonify({"error": "admin only"}), 403
        users = user_model.query.all()
        roles = defaultdict(int)
        for u in users:
            roles[u.role] += 1
        month_ago = datetime.utcnow() - timedelta(days=30)
        mau = sum(1 for u in users if u.last_seen and u.last_seen >= month_ago)
        pending = (approval_queue_item_model.query.filter_by(status="pending").count()
                   + alumni_verification_model.query.filter_by(status="pending").count()
                   + user_model.query.filter_by(role="business", business_approved=False).count())
        return jsonify({
            "usersByType": [
                {"label": "Students", "count": roles["trade"]},
                {"label": "Alumni", "count": roles["grad"]},
                {"label": "Businesses", "count": roles["business"]},
                {"label": "Admins", "count": roles["admin"]},
            ],
            "totals": {"users": len(users), "mau": mau,
                       "flagged": post_model.query.filter_by(flagged=True, removed=False).count(),
                       "pendingApprovals": pending},
            "registrationSeries": daily_series([u.created_at for u in users]),
            "content": {
                "posts": post_model.query.filter_by(removed=False).count(),
                "videos": post_model.query.filter(post_model.media.is_(True),
                                                       post_model.removed.is_(False)).count(),
                "opportunities": opportunity_model.query.count(),
                "events": event_model.query.count(),
            },
            "pipeline": {
                "listingQueue": approval_queue_item_model.query.filter_by(status="pending").count(),
                "alumniQueue": alumni_verification_model.query.filter_by(status="pending").count(),
                "businessVerifications":
                    user_model.query.filter_by(role="business", business_approved=False).count(),
            },
        })

    return blueprint
