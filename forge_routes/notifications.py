"""Notification read routes; creation and realtime delivery stay in the entrypoint."""

from flask import Blueprint, jsonify


def create_notifications_blueprint(*, db, require_login, notification_model):
    """Use the existing model and login guard, keeping ownership checks local."""
    blueprint = Blueprint("notifications", __name__)

    @blueprint.get("/api/notifications")
    def get_notifications():
        user, err = require_login()
        if err:
            return err
        notes = (notification_model.query.filter_by(user_id=user.id)
                 .order_by(notification_model.id.desc()).limit(50).all())
        unread = notification_model.query.filter_by(user_id=user.id, read=False).count()
        return jsonify({"notifications": [n.to_dict() for n in notes],
                        "unreadCount": unread})

    @blueprint.post("/api/notifications/<int:note_id>/read")
    def mark_notification_read(note_id):
        user, err = require_login()
        if err:
            return err
        note = notification_model.query.get_or_404(note_id)
        if note.user_id != user.id:
            return jsonify({"error": "not yours"}), 403
        note.read = True
        db.session.commit()
        return jsonify({"ok": True})

    @blueprint.post("/api/notifications/read-all")
    def mark_all_notifications_read():
        user, err = require_login()
        if err:
            return err
        notification_model.query.filter_by(user_id=user.id, read=False).update({"read": True})
        db.session.commit()
        return jsonify({"ok": True})

    return blueprint
