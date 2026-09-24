"""Role-specific onboarding routes using the existing session and persistence policy."""

from flask import Blueprint, jsonify


def create_onboarding_blueprint(*, db, require_login, steps_by_role):
    """Receive the existing dependencies without importing the app entrypoint."""
    blueprint = Blueprint("onboarding", __name__)

    @blueprint.get("/api/onboarding")
    def get_onboarding():
        user, err = require_login()
        if err:
            return err
        steps = steps_by_role.get(user.role, ["welcome"])
        return jsonify({"steps": steps, "step": user.onboarding_step,
                        "complete": user.onboarding_complete})

    @blueprint.post("/api/onboarding/advance")
    def advance_onboarding():
        user, err = require_login()
        if err:
            return err
        steps = steps_by_role.get(user.role, ["welcome"])
        user.onboarding_step = min(user.onboarding_step + 1, len(steps) - 1)
        if user.onboarding_step >= len(steps) - 1:
            user.onboarding_complete = True
        db.session.commit()
        return jsonify({"steps": steps, "step": user.onboarding_step,
                        "complete": user.onboarding_complete})

    @blueprint.post("/api/onboarding/skip")
    def skip_onboarding():
        user, err = require_login()
        if err:
            return err
        user.onboarding_complete = True
        db.session.commit()
        return jsonify({"steps": steps_by_role.get(user.role, ["welcome"]),
                        "step": user.onboarding_step, "complete": True})

    return blueprint
