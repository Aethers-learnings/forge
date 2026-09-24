"""Profile workflows using the existing session, models, and completion policy."""

from flask import Blueprint, jsonify, request


def create_profile_blueprint(*, db, require_login, student_roles, extract_skills,
                             recalc_completion, notification_model,
                             coach_message_model, application_model):
    """Receive existing dependencies without importing the app entrypoint."""
    blueprint = Blueprint("profile", __name__)

    @blueprint.post("/api/profile/cv-upload")
    def cv_upload():
        """NLP-assisted profile building (brief §2.8): accepts raw CV text and
        extracts skills. Empty body still just marks the CV uploaded."""
        user, err = require_login()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        cv_text = data.get("cvText") or ""
        newly_found = [s for s in extract_skills(cv_text) if s.lower() not in user.skills.lower()]
        if newly_found:
            merged = [s for s in user.skills.split(",") if s] + newly_found
            user.skills = ",".join(merged)
        user.cv_uploaded = True
        recalc_completion(user)
        db.session.commit()
        return jsonify(user.to_public())


    @blueprint.patch("/api/profile/skills")
    def update_skills():
        """Manual skill add/remove, independent of CV extraction."""
        user, err = require_login()
        if err:
            return err
        if user.role not in student_roles:
            return jsonify({"error": "skills apply to student and alumni accounts"}), 400
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        skill = (data.get("skill") or "").strip()
        if action not in ("add", "remove") or not skill:
            return jsonify({"error": "action ('add'/'remove') and skill are required"}), 400
        current = [s for s in user.skills.split(",") if s]
        if action == "add":
            if skill.lower() not in (c.lower() for c in current):
                current.append(skill)
        else:
            current = [c for c in current if c.lower() != skill.lower()]
        user.skills = ",".join(current)
        recalc_completion(user)
        db.session.commit()
        return jsonify(user.to_public())


    @blueprint.patch("/api/profile/portfolio")
    def update_portfolio():
        """Editable profile fields. Students/alumni edit the portfolio block;
        business users edit the company profile block — role decides which
        keys are honoured."""
        user, err = require_login()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        student_fields = (("bio", "bio"), ("headline", "headline"), ("programme", "programme"),
                          ("year", "year"), ("campus", "campus"), ("github", "github_url"),
                          ("linkedin", "linkedin_url"), ("credly", "credly_url"),
                          ("website", "portfolio_url"))
        business_fields = (("bio", "bio"), ("headline", "headline"), ("industry", "industry"),
                           ("companyDescription", "company_desc"), ("location", "location"),
                           ("talentSought", "talent_sought"), ("website", "portfolio_url"))
        fields = student_fields if user.role in student_roles else (
            business_fields if user.role == "business" else (("bio", "bio"),))
        for key, attr in fields:
            if key in data:
                setattr(user, attr, (data.get(key) or "").strip())
        recalc_completion(user)
        db.session.commit()
        return jsonify(user.to_public())


    @blueprint.patch("/api/profile/visibility")
    def update_visibility():
        user, err = require_login()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        for key, attr in (("profileVisible", "profile_visible"),
                          ("showEmail", "show_email"),
                          ("showSkills", "show_skills")):
            if key in data:
                setattr(user, attr, bool(data.get(key)))
        db.session.commit()
        return jsonify(user.to_public())


    @blueprint.get("/api/profile/export")
    def export_profile():
        """POPIA s23 'right of access' — one JSON download containing
        everything the platform holds on the requesting user."""
        user, err = require_login()
        if err:
            return err
        payload = user.to_public()
        payload["raw"] = {
            "email": user.email, "headline": user.headline, "programme": user.programme,
            "year": user.year, "campus": user.campus, "industry": user.industry,
            "companyDescription": user.company_desc, "location": user.location,
            "talentSought": user.talent_sought,
            "createdAt": user.created_at.isoformat() if user.created_at else None,
        }
        payload["notifications"] = [n.to_dict() for n in
                                    notification_model.query.filter_by(user_id=user.id)
                                    .order_by(notification_model.id).all()]
        payload["coachHistory"] = [m.to_dict() for m in
                                   coach_message_model.query.filter_by(user_id=user.id)
                                   .order_by(coach_message_model.id).all()]
        payload["applications"] = [{"opportunityId": a.opportunity_id,
                                    "at": a.created_at.isoformat()}
                                   for a in application_model.query.filter_by(user_id=user.id).all()]
        resp = jsonify(payload)
        resp.headers["Content-Disposition"] = 'attachment; filename="forge-my-data.json"'
        return resp

    return blueprint
