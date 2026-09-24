"""Behavior baseline for the bounded T-203 profile extraction (Issue #3)."""

from datetime import datetime

import pytest

import forge_backend as backend


ROUTES = [
    ("POST", "/api/profile/cv-upload"),
    ("PATCH", "/api/profile/skills"),
    ("PATCH", "/api/profile/portfolio"),
    ("PATCH", "/api/profile/visibility"),
    ("GET", "/api/profile/export"),
]


def make_user(username="profile", role="grad", **fields):
    user = backend.User(username=username, name=username, role=role,
                        password_hash="unused: session established by test", **fields)
    backend.db.session.add(user)
    backend.db.session.commit()
    return user


def sign_in(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user.id
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return {"Origin": "http://localhost", "X-CSRF-Token": response.json["csrfToken"]}


@pytest.mark.parametrize("method,path", ROUTES)
def test_profile_routes_require_login(client, method, path):
    response = client.open(path, method=method)
    assert response.status_code == 401
    assert response.json == {"error": "not authenticated"}


@pytest.mark.parametrize("method,path", ROUTES)
def test_profile_routes_reject_suspended_users(client, method, path):
    user = make_user()
    headers = sign_in(client, user)
    user.suspended = True
    backend.db.session.commit()
    response = client.open(path, method=method, headers=headers)
    assert response.status_code == 403
    assert response.json == {"error": "account suspended — contact the administrator"}


@pytest.mark.parametrize("method,path", ROUTES[:-1])
@pytest.mark.parametrize("failure", ["missing-token", "foreign-origin"])
def test_profile_mutations_keep_global_csrf_guard(client, method, path, failure):
    user = make_user()
    headers = sign_in(client, user)
    before = user.to_public()
    if failure == "missing-token":
        headers.pop("X-CSRF-Token")
    else:
        headers["Origin"] = "https://foreign.example"
    response = client.open(path, method=method, headers=headers, json={
        "cvText": "Python", "action": "add", "skill": "Python",
        "bio": "Changed", "profileVisible": False,
    })
    assert response.status_code == 403
    assert response.json["code"] == "csrf_failed"
    backend.db.session.refresh(user)
    assert user.to_public() == before


@pytest.mark.parametrize("role", ["trade", "grad", "business", "admin"])
def test_cv_extraction_keeps_keyword_order_substrings_and_existing_skills(client, role):
    user = make_user(role=role, skills="custom,,PYTHON,NoSQL")
    headers = sign_in(client, user)
    other = make_user("other", skills="private")
    # Substring matching (including SQL in NoSQL and React in reactive) is intentional baseline.
    response = client.post("/api/profile/cv-upload", headers=headers, json={
        "cvText": "FLASK flask reactive SQL python TIG WELDING", "userId": other.id,
    })
    assert response.status_code == 200
    assert response.json["skills"] == ["custom", "PYTHON", "NoSQL", "TIG welding", "React", "Flask"]
    assert response.json["cvUploaded"] is True
    assert response.json["completion"] == 20
    backend.db.session.refresh(user)
    assert user.skills == "custom,PYTHON,NoSQL,TIG welding,React,Flask"
    assert response.json == user.to_public()
    repeated = client.post("/api/profile/cv-upload", headers=headers,
                           json={"cvText": "FLASK SQL python TIG WELDING reactive"})
    assert repeated.json == response.json
    backend.db.session.refresh(other)
    assert (other.skills, other.cv_uploaded) == ("private", False)


@pytest.mark.parametrize("body", [None, "{", "null", "{}", '{"cvText": null}'])
def test_empty_or_malformed_cv_body_still_marks_uploaded(client, body):
    user = make_user()
    response = client.post("/api/profile/cv-upload", headers=sign_in(client, user),
                           data=body, content_type="application/json")
    assert response.status_code == 200
    assert response.json["skills"] == []
    assert response.json["cvUploaded"] is True
    assert response.json["completion"] == 10
    backend.db.session.refresh(user)
    assert (user.skills, user.cv_uploaded, user.completion) == ("", True, 10)


@pytest.mark.parametrize("role", ["trade", "grad"])
def test_skills_case_insensitive_add_remove_and_completion(client, role):
    user = make_user(role=role, skills="Python,,SQL")
    headers = sign_in(client, user)
    for action, skill, expected, completion in [
        ("add", " python ", ["Python", "SQL"], 10),
        ("add", " Rust ", ["Python", "SQL", "Rust"], 10),
        ("remove", "pYtHoN", ["SQL", "Rust"], 10),
        ("remove", "missing", ["SQL", "Rust"], 10),
        ("remove", "sql", ["Rust"], 10),
        ("remove", "rust", [], 0),
    ]:
        response = client.patch("/api/profile/skills", headers=headers,
                                json={"action": action, "skill": skill})
        assert response.status_code == 200
        assert response.json["skills"] == expected
        assert response.json["completion"] == completion
        backend.db.session.refresh(user)
        assert user.skills == ",".join(expected)
        assert response.json == user.to_public()


@pytest.mark.parametrize("role", ["business", "admin"])
def test_skills_reject_nonstudent_roles_before_body_validation(client, role):
    user = make_user(role=role)
    response = client.patch("/api/profile/skills", headers=sign_in(client, user))
    assert response.status_code == 400
    assert response.json == {"error": "skills apply to student and alumni accounts"}


@pytest.mark.parametrize("body", [{}, {"action": "rename", "skill": "Python"},
                                 {"action": "add", "skill": "  "}])
def test_skills_validation_does_not_mutate_profile(client, body):
    user = make_user(skills="Python")
    response = client.patch("/api/profile/skills", headers=sign_in(client, user), json=body)
    assert response.status_code == 400
    assert response.json == {"error": "action ('add'/'remove') and skill are required"}
    backend.db.session.refresh(user)
    assert (user.skills, user.completion) == ("Python", 72)


@pytest.mark.parametrize("role,completion", [("trade", 90), ("grad", 90),
                                           ("business", 50), ("admin", 30)])
def test_portfolio_allowlist_trimming_clearing_and_session_identity(client, role, completion):
    user = make_user(role=role, email="owner@example.test", skills="Python")
    other = make_user("other", bio="untouched")
    headers = sign_in(client, user)
    student = {"programme": "programme", "year": "year", "campus": "campus",
               "github": "github_url", "linkedin": "linkedin_url", "credly": "credly_url"}
    business = {"industry": "industry", "companyDescription": "company_desc",
                "location": "location", "talentSought": "talent_sought"}
    common = {"bio": "bio", "headline": "headline", "website": "portfolio_url"}
    fields = {**student, **business, **common}
    payload = {key: f"  {key} value  " for key in fields}
    payload.update(userId=other.id, role="admin", name="forged", email="forged",
                   skills="forged", completion=100, businessApproved=True)
    response = client.patch("/api/profile/portfolio", headers=headers, json=payload)
    assert response.status_code == 200
    allowed = ({**student, **common} if role in ("trade", "grad") else
               {**business, **common} if role == "business" else {"bio": "bio"})
    backend.db.session.refresh(user)
    for key, attr in fields.items():
        assert getattr(user, attr) == (f"{key} value" if key in allowed else "")
    assert (user.role, user.name, user.email, user.skills, user.business_approved) == (
        role, "profile", "owner@example.test", "Python", False)
    assert response.json["completion"] == completion
    assert response.json == user.to_public()
    cleared = client.patch("/api/profile/portfolio", headers=headers, json={"bio": None})
    assert cleared.json["bio"] == ""
    assert cleared.json["completion"] == completion - 10
    assert cleared.json["headline"] == response.json["headline"]
    backend.db.session.refresh(other)
    assert other.bio == "untouched"


@pytest.mark.parametrize("role", ["trade", "grad", "business", "admin"])
def test_visibility_preserves_truthiness_partial_updates_and_completion(client, role):
    user = make_user(role=role, skills="Python", email="private@example.test")
    headers = sign_in(client, user)
    response = client.patch("/api/profile/visibility", headers=headers, json={
        "profileVisible": "false", "showEmail": [], "showSkills": None, "completion": 0,
    })
    assert response.status_code == 200
    assert response.json["visibility"] == {
        "profileVisible": True, "showEmail": False, "showSkills": False,
    }
    assert response.json["completion"] == 72  # Visibility never recalculates completion.
    backend.db.session.refresh(user)
    assert response.json == user.to_public()
    response = client.patch("/api/profile/visibility", headers=headers,
                            json={"profileVisible": False, "showEmail": 1})
    assert response.json["visibility"] == {
        "profileVisible": False, "showEmail": True, "showSkills": False,
    }
    assert response.json["completion"] == 72
    assert client.get(f"/api/users/{user.id}").status_code == 200
    viewer = make_user("viewer")
    sign_in(client, viewer)
    hidden = client.get(f"/api/users/{user.id}")
    assert hidden.status_code == 404
    assert hidden.json == {"error": "profile not visible"}


@pytest.mark.parametrize("path,completion", [("portfolio", 10), ("visibility", 72)])
def test_malformed_profile_patch_is_existing_noop_except_completion(client, path, completion):
    user = make_user(bio="existing")
    response = client.patch(f"/api/profile/{path}", headers=sign_in(client, user),
                            data="{", content_type="application/json")
    assert response.status_code == 200
    assert response.json["bio"] == "existing"
    assert response.json["completion"] == completion


@pytest.mark.parametrize("role", ["trade", "grad", "business", "admin"])
def test_export_contains_only_caller_data_with_full_history_and_attachment(client, role):
    when = datetime(2026, 1, 2, 3, 4, 5)
    user = make_user(role=role, email="private@example.test", created_at=when,
                     headline="Headline", programme="Programme", year="Year", campus="Campus",
                     industry="Industry", company_desc="Description", location="Location",
                     talent_sought="Talent", profile_visible=False, show_skills=False,
                     skills="Python", reset_token="private-reset-digest")
    other = make_user("other")
    sign_in(client, user)
    notes = [backend.Notification(user_id=user.id, type="test", text=str(i),
                                  read=i % 2 == 0, link="/profile", created_at=when)
             for i in range(52)]
    messages = [backend.CoachMessage(user_id=user.id, who=who, text=text)
                for who, text in [("user", "Question"), ("ai", "Answer")]]
    opp = backend.Opportunity(title="Role", co="Company")
    backend.db.session.add_all(notes + messages + [opp])
    backend.db.session.flush()
    application = backend.Application(user_id=user.id, opportunity_id=opp.id, created_at=when)
    backend.db.session.add_all([
        application,
        backend.Application(user_id=other.id, opportunity_id=opp.id),
        backend.Notification(user_id=other.id, type="private", text="Other notification"),
        backend.CoachMessage(user_id=other.id, who="user", text="Other history"),
    ])
    backend.db.session.commit()
    expected = user.to_public()
    expected.update(raw={
        "email": "private@example.test", "headline": "Headline", "programme": "Programme",
        "year": "Year", "campus": "Campus", "industry": "Industry",
        "companyDescription": "Description", "location": "Location", "talentSought": "Talent",
        "createdAt": when.isoformat(),
    }, notifications=[n.to_dict() for n in notes],
        coachHistory=[{"who": "user", "text": "Question"}, {"who": "ai", "text": "Answer"}],
        applications=[{"opportunityId": opp.id, "at": when.isoformat()}])
    response = client.get(f"/api/profile/export?userId={other.id}")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"] == 'attachment; filename="forge-my-data.json"'
    assert response.json == expected  # Exact keys also exclude password/reset credentials.
    backend.db.session.refresh(notes[1])
    assert notes[1].read is False


def test_export_empty_collections_and_nullable_creation_date(client):
    user = make_user()
    sign_in(client, user)
    user.created_at = None
    backend.db.session.commit()
    response = client.get("/api/profile/export")
    assert response.status_code == 200
    assert response.json["raw"]["createdAt"] is None
    for key in ("notifications", "coachHistory", "applications"):
        assert response.json[key] == []


def test_profile_route_methods_include_existing_head_and_options(app):
    expected = {path: {method, "OPTIONS"} | ({"HEAD"} if method == "GET" else set())
                for method, path in ROUTES}
    actual = [(rule.rule, rule.methods) for rule in app.url_map.iter_rules() if rule.rule in expected]
    assert len(actual) == len(expected)
    assert dict(actual) == expected
