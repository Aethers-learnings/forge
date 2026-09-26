"""Behavior baseline for the bounded T-203 analytics extraction."""
from datetime import datetime, timedelta

import pytest
import forge_backend as backend


NOW = datetime(2026, 9, 26, 12)
PATHS = [f"/api/analytics/{kind}" for kind in ("student", "business", "admin")]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return NOW
    monkeypatch.setattr(backend, "datetime", Clock)
    # The extracted module owns its clock import; keep both clocks identical.
    import sys
    module = sys.modules.get("forge_routes.analytics")
    if module:
        monkeypatch.setattr(module, "datetime", Clock)


def user(name, role="trade", **kwargs):
    row = backend.User(username=name, name=name, role=role,
                       password_hash="unused", created_at=NOW, **kwargs)
    backend.db.session.add(row)
    backend.db.session.commit()
    return row


def login(client, row):
    with client.session_transaction() as session:
        session["user_id"] = row.id


def series(counts=None):
    counts = counts or {}
    return [{"date": (NOW - timedelta(days=i)).date().isoformat(),
             "count": counts.get(i, 0)} for i in range(13, -1, -1)]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("state", ["anonymous", "missing", "suspended"])
def test_authentication(client, path, state):
    if state == "missing":
        with client.session_transaction() as session:
            session["user_id"] = 999
    elif state == "suspended":
        login(client, user("blocked", suspended=True))
    response = client.get(path)
    assert response.status_code == (403 if state == "suspended" else 401)
    assert response.json == {"error": "account suspended — contact the administrator"
                            if state == "suspended" else "not authenticated"}


@pytest.mark.parametrize("role", ["trade", "grad", "business", "admin"])
@pytest.mark.parametrize("kind", ["student", "business", "admin"])
def test_role_gates(client, role, kind):
    login(client, user("caller", role))
    allowed = kind == "student" or role == "admin" or (kind == "business" and role == "business")
    response = client.get(f"/api/analytics/{kind}")
    assert response.status_code == (200 if allowed else 403)
    if not allowed:
        assert response.json == {"error": "business or admin only" if kind == "business" else "admin only"}


def test_empty_responses_and_methods(client, app):
    caller = user("caller", "admin", completion=42)
    login(client, caller)
    assert client.get(PATHS[0]).json == {
        "profileViews": {"total": 0, "series": series()},
        "connections": {"total": 0, "series": series()},
        "engagement": {"posts": 0, "likes": 0, "comments": 0},
        "peerComparison": {"me": 42, "programmeAvg": None, "programme": ""},
        "topSearchedSkills": [],
    }
    assert client.get(PATHS[1]).json == {
        "pipeline": [], "engagement": {"impressions": 0, "applications": 0, "rate": "—"},
        "skillDistribution": [], "demographics": {"byProgramme": [], "byYear": []},
        "reach": {"profileViews": 0, "impressions": 0},
    }
    assert client.get(PATHS[2]).json == {
        "usersByType": [{"label": label, "count": int(label == "Admins")}
                        for label in ("Students", "Alumni", "Businesses", "Admins")],
        "totals": {"users": 1, "mau": 1, "flagged": 0, "pendingApprovals": 0},
        "registrationSeries": series({0: 1}),
        "content": {"posts": 0, "videos": 0, "opportunities": 0, "events": 0},
        "pipeline": {"listingQueue": 0, "alumniQueue": 0, "businessVerifications": 0},
    }
    rules = [r for r in app.url_map.iter_rules() if r.rule in PATHS]
    assert len(rules) == 3
    assert all(r.methods == {"GET", "HEAD", "OPTIONS"} for r in rules)
    assert caller.last_seen == NOW  # Existing login guard still commits activity.


def test_student_scope_series_engagement_peers_and_search_order(client):
    caller = user("caller", programme="Software", completion=80,
                  skills=" Python, SQL,React,Flask,Figma,JavaScript ")
    other = user("other", programme="Software", completion=51, suspended=True)
    user("peer", programme="Software", completion=60)
    user("other-role", "grad", programme="Software", completion=100)
    user("other-programme", programme="Design", completion=100)
    rows = [backend.ProfileView(viewed_user_id=caller.id, created_at=NOW - timedelta(days=d))
            for d in (0, 0, 13, 14)]
    rows += [backend.ProfileView(viewed_user_id=other.id, created_at=NOW)]
    rows += [backend.NetworkRequest(name=str(d), role="grad", status="accepted",
                                    created_at=NOW - timedelta(days=d)) for d in (0, 2, 14)]
    rows += [backend.NetworkRequest(name="pending", role="grad", status="pending"),
             backend.ConnectionNPC(name="shared", role="grad")]
    own = backend.Post(author_name=caller.name, author_role="grad", feed="grad", body="same name", base_likes=3)
    removed = backend.Post(author_name=caller.name, author_role="trade", feed="trade", body="removed", removed=True, base_likes=99)
    rows += [own, removed, backend.Post(author_name=other.name, author_role="trade", feed="trade", body="other")]
    rows += [backend.SkillSearch(skill=s) for s in
             ["SQL", "Python", "Python", "python", "React", "Flask", "Figma", "JavaScript", " Python", "Rust"]]
    backend.db.session.add_all(rows)
    backend.db.session.flush()
    backend.db.session.add_all([
        backend.Like(post_id=own.id, user_id=other.id),
        backend.Comment(post_id=own.id, author_name="any", text="hello"),
        backend.Comment(post_id=removed.id, author_name="any", text="excluded"),
    ])
    backend.db.session.commit()
    login(client, caller)
    assert client.get(PATHS[0] + f"?user_id={other.id}").json == {
        "profileViews": {"total": 4, "series": series({0: 2, 13: 1})},
        "connections": {"total": 4, "series": series({2: 1, 1: 1, 0: 2})},
        "engagement": {"posts": 1, "likes": 4, "comments": 1},
        "peerComparison": {"me": 80, "programmeAvg": 55, "programme": "Software"},
        "topSearchedSkills": [{"skill": s, "count": c} for s, c in
                              [("Python", 2), ("SQL", 1), ("python", 1), ("React", 1), ("Flask", 1)]],
    }


@pytest.mark.parametrize("impressions,rate", [(0, "—"), (8, "38%"), (2, "150%")])
def test_application_rows_distributions_pipeline_and_rounding(client, impressions, rate):
    owner = user("owner", "business")  # Approval is not required for analytics.
    applicant = user("applicant", skills=" Python,SQL,Python, ", programme="Software", year="2")
    unspecified = user("unspecified", "grad")
    listing = backend.BusinessListing(owner_user_id=owner.id, title="listing", impressions=impressions)
    opps = [backend.Opportunity(owner_user_id=owner.id, title=t, co="Forge") for t in ("Zulu", "Alpha", "Empty")]
    backend.db.session.add_all([listing, *opps])
    backend.db.session.flush()
    backend.db.session.add_all([
        backend.Application(opportunity_id=opps[0].id, user_id=applicant.id),
        backend.Application(opportunity_id=opps[1].id, user_id=applicant.id),
        backend.Application(opportunity_id=opps[1].id, user_id=unspecified.id),
    ])
    backend.db.session.commit()
    login(client, owner)
    assert client.get(PATHS[1]).json == {
        "pipeline": [{"title": t, "applicants": n, "status": "live"}
                     for t, n in [("Zulu", 1), ("Alpha", 2), ("Empty", 0)]],
        "engagement": {"impressions": impressions, "applications": 3, "rate": rate},
        "skillDistribution": [{"label": "Python", "count": 4}, {"label": "SQL", "count": 2}],
        "demographics": {
            "byProgramme": [{"label": "Software", "count": 2}, {"label": "Unspecified", "count": 1}],
            "byYear": [{"label": "2", "count": 2}, {"label": "Unspecified", "count": 1}],
        },
        "reach": {"profileViews": 0, "impressions": impressions},
    }


def test_admin_mau_boundary_pending_composition_and_content(client):
    admin = user("admin", "admin")
    user("boundary", last_seen=NOW - timedelta(days=30), suspended=True)
    user("outside", last_seen=NOW - timedelta(days=30, microseconds=1))
    grad = user("grad", "grad", last_seen=None)
    business = user("pending", "business", last_seen=NOW)
    user("approved", "business", business_approved=True, last_seen=None)
    grad.created_at = NOW - timedelta(days=14)
    business.created_at = NOW - timedelta(days=13)
    backend.db.session.add_all([
        backend.ApprovalQueueItem(title=s, co="Forge", status=s) for s in ("pending", "pending", "approved", "rejected")
    ] + [backend.AlumniVerification(user_id=grad.id, document_ref=s, status=s) for s in ("pending", "approved", "rejected")]
      + [backend.Post(author_name="any", author_role="trade", feed="trade", body="post", media=m, removed=r, flagged=f)
         for m, r, f in [(False, False, True), (True, False, False), (True, True, True)]]
      + [backend.Opportunity(title="all-time", co="Forge"), backend.Event(title="event", place="here", day="1", mon="Jan")])
    backend.db.session.commit()
    login(client, admin)
    assert client.get(PATHS[2]).json == {
        "usersByType": [{"label": label, "count": n} for label, n in
                        [("Students", 2), ("Alumni", 1), ("Businesses", 2), ("Admins", 1)]],
        "totals": {"users": 6, "mau": 3, "flagged": 1, "pendingApprovals": 4},
        "registrationSeries": series({0: 4, 13: 1}),
        "content": {"posts": 2, "videos": 1, "opportunities": 1, "events": 1},
        "pipeline": {"listingQueue": 2, "alumniQueue": 1, "businessVerifications": 1},
    }


def test_impressions_are_cumulative_linked_listing_student_board_reads(client):
    owner = user("owner", "business")
    student = user("student")
    grad = user("grad", "grad")
    admin = user("admin", "admin")
    queue = backend.ApprovalQueueItem(title="approved", co="Forge", status="approved")
    backend.db.session.add(queue)
    backend.db.session.flush()
    live = backend.BusinessListing(owner_user_id=owner.id, queue_item_id=queue.id,
                                   title="live", status="live", impressions=10)
    hidden = backend.BusinessListing(owner_user_id=owner.id, title="hidden", status="pending")
    backend.db.session.add_all([live, hidden])
    backend.db.session.flush()
    backend.db.session.add_all([
        backend.Opportunity(title=t, co="Forge", owner_user_id=owner.id, listing_id=listing_id)
        for t, listing_id in [("first", live.id), ("second", live.id), ("hidden", hidden.id), ("legacy", None)]
    ])
    backend.db.session.commit()
    for reader in (student, student, grad, owner, admin):
        login(client, reader)
        assert client.get("/api/opportunities").status_code == 200
    login(client, owner)
    for _ in range(2):
        assert client.get(PATHS[1]).json["engagement"] == {
            "applications": 0, "impressions": 13, "rate": "0%"}
    backend.db.session.refresh(hidden)
    assert hidden.impressions == 0
