"""Ownership-v2 HTTP translation behind a process-wide exclusive social mode."""

from functools import wraps
from itsdangerous import BadSignature, URLSafeSerializer
from flask import jsonify, request

from forge_routes.owned_social import (
    Conflict, Forbidden, Invalid, NotFound, OperationUnavailable,
    OwnedSocialService, PreconditionRequired,
)


def create_social_dispatch(app, db, models, require_login, mode, *, emit=None):
    # Captured at registration: a capability header cannot change graph mode.
    signer = URLSafeSerializer(app.secret_key, salt="forge-social-cursor-v2")
    service = lambda: OwnedSocialService(db.engine, models, emit=emit)

    @app.get("/api/social-config")
    def social_config():
        # Public process configuration only; never an authorization signal.
        response = jsonify(mode=mode)
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(exc):
        if isinstance(exc, PreconditionRequired):
            return jsonify(error="expected version required"), 428
        if isinstance(exc, NotFound):
            return jsonify(error="not found"), 404
        if isinstance(exc, Forbidden):
            return jsonify(error="forbidden"), 403
        if isinstance(exc, OperationUnavailable):
            return jsonify(error="operation unavailable"), 409
        if isinstance(exc, Conflict):
            return jsonify(error="conflict"), 409
        return jsonify(error="invalid request"), 400

    def safe(fn):
        @wraps(fn)
        def run(user, *args):
            try:
                if any(len(request.args.getlist(key)) != 1 for key in request.args):
                    raise Invalid("ambiguous query parameter")
                return fn(service(), user, *args)
            except (PreconditionRequired, NotFound, Forbidden, OperationUnavailable, Conflict, Invalid) as exc:
                return error(exc)
        return run

    def body(keys):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(keys):
            raise Invalid("invalid request body")
        if "expectedVersion" in keys and "expectedVersion" not in data:
            raise PreconditionRequired("expected version required")
        if set(data) != set(keys):
            raise Invalid("invalid request body")
        return data

    def version(value):
        if value is None:
            raise PreconditionRequired("expected version required")
        if type(value) is not int or value < 0:
            raise Invalid("invalid expected version")
        return value

    def positive(value):
        if type(value) is not int or value < 1:
            raise Invalid("invalid identifier")
        return value

    def page_limit(key, default=50):
        raw = request.args.get(key)
        if raw is None:
            return default
        if not raw.isdecimal() or not 1 <= int(raw) <= 50:
            raise Invalid("invalid limit")
        return int(raw)

    def cursor(token, user, scope):
        if not isinstance(token, str) or not token or len(token) > 1024:
            raise Invalid("invalid cursor")
        try:
            data = signer.loads(token)
            if (type(data) is not list or len(data) != 3 or data[0] != user.id
                    or data[1] != scope or type(data[2]) is not int or data[2] < 1):
                raise Invalid("invalid cursor")
            return data[2]
        except (BadSignature, ValueError, TypeError):
            raise Invalid("invalid cursor") from None

    def encode(user, scope, position):
        return signer.dumps([user.id, scope, position])

    def message(row, user):
        return {"sequence": row["seq"], "who": "me" if row["sender_id"] == user.id else "them",
                "text": row["text"], "createdAt": row["created_at"].isoformat() + "Z"}

    def detail(svc, user, slug, before=None, limit=50):
        history = svc.history(user, slug, before=before, limit=limit)
        info = svc.conversation_info(user, slug)
        messages = [message(row, user) for row in history["messages"]]
        return {"id": slug, "name": info["name"], "color": info["color"],
                "unread": history["unread_count"] > 0, "unreadCount": history["unread_count"],
                "messages": messages, "hasMore": history["has_more"],
                "nextCursor": encode(user, "history:" + slug, history["messages"][0]["seq"])
                if history["has_more"] and messages else None,
                "lastSequence": history["last_seq"],
                "lastReadSequence": history["last_read_seq"], "readOnly": info["read_only"]}

    @safe
    def network(svc, user):
        allowed = {"requests", "outgoingRequests", "connections", "suggested"}
        if any(key not in {"limit", *(name + "Limit" for name in allowed),
                           *(name + "Cursor" for name in allowed)} for key in request.args):
            raise Invalid("unknown query parameter")
        base_limit = page_limit("limit")
        limits = {name: page_limit(name + "Limit", base_limit) for name in allowed}
        after = {name: cursor(request.args[name + "Cursor"], user, "network:" + name)
                 for name in allowed if name + "Cursor" in request.args}
        sections = svc.network_sections(user, after=after, limit=limits)
        result = {"requests": [], "outgoingRequests": [], "suggested": [],
                  "connections": [], "nextCursors": {}}
        for name in ("requests", "outgoingRequests", "connections"):
            rows, more = sections[name]
            for edge in rows:
                peer_id = edge["user_high_id"] if edge["user_low_id"] == user.id else edge["user_low_id"]
                peer = db.session.get(models.User, peer_id)
                item = {"id": edge["id"], "counterpartUserId": peer_id,
                        "name": peer.name if peer else "Member", "color": peer.color if peer else "",
                        "role": peer.role if peer else "", "direction": "outgoing" if edge["requester_id"] == user.id else "incoming",
                        "version": edge["version"], "status": edge["state"],
                        "blockVersion": edge.get("block_version", 0)}
                if name == "connections":
                    status = svc.endorsement_status(user, edge["id"])
                    item.update({"endorsements": status["endorsements"],
                                 "endorsedByMe": status["endorsedByMe"],
                                 "endorsementVersion": status["version"]})
                result[name].append(item)
            if more:
                result["nextCursors"][name] = encode(user, "network:" + name, rows[-1]["id"])
        suggestions = svc.suggestions(user)
        suggestions = [p for p in suggestions if p["id"] > after.get("suggested", 0)]
        selected = suggestions[:limits["suggested"]]
        result["suggested"] = [{**p, "edgeVersion": p.pop("edge_version"),
                                "blockVersion": p.pop("block_version")}
                               for p in selected]
        if len(suggestions) > len(selected):
            result["nextCursors"]["suggested"] = encode(user, "network:suggested", selected[-1]["id"])
        return jsonify(result)

    @safe
    def connect(svc, user, target):
        data = body({"expectedVersion"})
        edge = svc.request(user, positive(target), version(data["expectedVersion"]))
        return jsonify(ok=True, requestId=edge["id"], version=edge["version"])

    @safe
    def transition(svc, user, edge_id, action):
        if action not in ("accept", "ignore", "cancel", "disconnect"):
            raise Invalid("unknown action")
        data = body({"expectedVersion"})
        edge = svc.transition(user, positive(edge_id), action, version(data["expectedVersion"]))
        return jsonify(ok=True, version=edge["version"])

    @safe
    def endorse(svc, user, edge_id):
        data = body({"endorsed", "expectedVersion"})
        if type(data["endorsed"]) is not bool:
            raise Invalid("invalid desired state")
        svc.endorse(user, positive(edge_id), data["endorsed"], version(data["expectedVersion"]))
        status = svc.endorsement_status(user, edge_id)
        return jsonify(id=edge_id, endorsements=status["endorsements"],
                       endorsedByMe=status["endorsedByMe"], version=status["version"])

    @safe
    def blocks(svc, user):
        if set(request.args) - {"limit", "cursor"}:
            raise Invalid("unknown query parameter")
        after = cursor(request.args["cursor"], user, "blocks") if "cursor" in request.args else None
        rows, more = svc.own_blocks(user, after=after, limit=page_limit("limit"))
        output = []
        for row in rows:
            peer = db.session.get(models.User, row["blocked_id"])
            output.append({
                "targetUserId": row["blocked_id"],
                "name": peer.name if peer else "Member",
                "version": row["version"],
            })
        response = jsonify(blocks=output,
                           nextCursor=encode(user, "blocks", rows[-1]["id"])
                           if more and rows else None)
        return response

    @safe
    def set_block(svc, user, target_id):
        data = body({"blocked", "expectedVersion"})
        if type(data["blocked"]) is not bool:
            raise Invalid("invalid desired state")
        row, created = svc.set_block(
            user, positive(target_id), data["blocked"],
            version(data["expectedVersion"]), with_status=True)
        return jsonify(ok=True, blocked=data["blocked"],
                       version=row["version"] if row else 0), 201 if created else 200

    @safe
    def conversations(svc, user):
        if set(request.args) - {"limit", "cursor"}:
            raise Invalid("unknown query parameter")
        after = cursor(request.args["cursor"], user, "conversations") if "cursor" in request.args else None
        rows, more = svc.list_conversations(user, after=after, limit=page_limit("limit"))
        output = []
        for row in rows:
            item = detail(svc, user, row["public_id"], limit=1)
            output.append(item)
        response = jsonify(output)
        if more:
            response.headers["X-Next-Cursor"] = encode(user, "conversations", rows[-1]["id"])
        return response

    @safe
    def conversation(svc, user, slug):
        if set(request.args) - {"before"}:
            raise Invalid("unknown query parameter")
        before = cursor(request.args["before"], user, "history:" + slug) if "before" in request.args else None
        return jsonify(detail(svc, user, slug, before))

    @safe
    def open_conversation(svc, user):
        data = body({"targetUserId"})
        row, created = svc.open_conversation(user, positive(data["targetUserId"]), with_status=True)
        return jsonify(detail(svc, user, row["public_id"])), 201 if created else 200

    @safe
    def send(svc, user, slug):
        data = body({"text", "clientMessageId"})
        if not isinstance(data["clientMessageId"], str) or len(data["clientMessageId"]) > 128:
            raise Invalid("invalid retry key")
        row, created = svc.send(user, slug, data["text"], data["clientMessageId"], with_status=True)
        info = svc.conversation_info(user, slug)
        return jsonify(conversationId=slug, message=message(row, user),
                       lastSequence=info["last_seq"]), 201 if created else 200

    @safe
    def read(svc, user, slug):
        data = body({"upToSequence"})
        last = svc.mark_read(user, slug, data["upToSequence"])
        history = svc.history(user, slug)
        return jsonify(lastReadSequence=last, unreadCount=history["unread_count"])

    import re
    patterns = [
        ("GET", re.compile(r"/api/network/blocks"), blocks),
        ("PUT", re.compile(r"/api/network/blocks/(\d+)"), set_block),
        ("GET", re.compile(r"/api/network"), network),
        ("POST", re.compile(r"/api/network/suggested/(\d+)/connect"), connect),
        ("POST", re.compile(r"/api/network/requests/(\d+)/(\w+)"), transition),
        ("POST", re.compile(r"/api/network/connections/(\d+)/endorse"), endorse),
        ("GET", re.compile(r"/api/conversations"), conversations),
        ("POST", re.compile(r"/api/conversations"), open_conversation),
        ("GET", re.compile(r"/api/conversations/([^/]+)"), conversation),
        ("POST", re.compile(r"/api/conversations/([^/]+)/messages"), send),
        ("POST", re.compile(r"/api/conversations/([^/]+)/read"), read),
    ]

    @app.before_request
    def exclusive_social_mode():
        for method, pattern, handler in patterns:
            match = pattern.fullmatch(request.path)
            if method != ("GET" if request.method == "HEAD" else request.method) or not match:
                continue
            if mode == "legacy":
                return None
            user, failure = require_login()
            if failure:
                return failure
            if mode == "maintenance":
                return jsonify(error="social maintenance"), 503
            if request.headers.get("X-Forge-Ownership-Version") != "2":
                return jsonify(error="ownership client update required"), 426
            return handler(user, *[int(v) if v.isdecimal() else v for v in match.groups()])
        return None

    @app.after_request
    def private_v2(response):
        if mode == "v2" and any(method == ("GET" if request.method == "HEAD" else request.method)
                                and pattern.fullmatch(request.path)
                                for method, pattern, _ in patterns):
            response.headers["Cache-Control"] = "no-store"
        return response
