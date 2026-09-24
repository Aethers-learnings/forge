"""T-101 authentication, authorization, ownership, visibility and approval regressions."""

import pytest
from werkzeug.security import generate_password_hash

import forge_backend as backend


def make_user(username, role="grad", **kwargs):
    user = backend.User(
        username=username,
        password_hash=generate_password_hash("password123"),
        role=role,
        name=kwargs.pop("name", username),
        **kwargs,
    )
    backend.db.session.add(user)
    backend.db.session.commit()
    return user


def sign_in(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user.id


def csrf_headers(client):
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return {
        "X-CSRF-Token": response.json["csrfToken"],
        "Origin": "http://localhost",
    }


# ---------------------------------------------------------------------------
# Registration and login
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["trade", "grad", "business"])
def test_public_registration_allows_only_self_register_roles(client, role):
    response = client.post(
        "/api/auth/register",
        json={
            "username": f"new-{role}",
            "password": "password123",
            "role": role,
            "email": "",
        },
    )

    assert response.status_code == 201
    user = backend.User.query.filter_by(username=f"new-{role}").one()
    assert user.role == role

    with client.session_transaction() as session:
        assert session["user_id"] == user.id


def test_public_registration_rejects_admin_role(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "self-admin",
            "password": "password123",
            "role": "admin",
        },
    )

    assert response.status_code == 400
    assert backend.User.query.filter_by(username="self-admin").first() is None


def test_student_registration_rejects_foreign_email_domain(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "student",
            "password": "password123",
            "role": "trade",
            "email": "student@example.com",
        },
    )

    assert response.status_code == 400
    assert backend.User.query.filter_by(username="student").first() is None


def test_registration_rejects_duplicate_username(client):
    make_user("taken")

    response = client.post(
        "/api/auth/register",
        json={
            "username": "taken",
            "password": "password123",
            "role": "grad",
        },
    )

    assert response.status_code == 409
    assert backend.User.query.filter_by(username="taken").count() == 1


def test_login_rejects_wrong_password_without_creating_session(client):
    make_user("alice")

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong"},
    )

    assert response.status_code == 401
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_login_rejects_suspended_user(client):
    make_user("alice", suspended=True)

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )

    assert response.status_code == 403
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_successful_login_establishes_correct_identity(client):
    user = make_user("alice")

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json["id"] == user.id

    with client.session_transaction() as session:
        assert session["user_id"] == user.id


# ---------------------------------------------------------------------------
# Role gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["trade", "grad"])
def test_student_roles_cannot_access_business_or_admin_surfaces(client, role):
    user = make_user(f"{role}-user", role=role)
    sign_in(client, user)

    assert client.get("/api/business/listings").status_code == 403
    assert client.get("/api/admin/queue").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/analytics/admin").status_code == 403
    assert client.get("/api/search/candidates").status_code == 403


def test_business_cannot_access_admin_surfaces(client):
    user = make_user("business", role="business", business_approved=True)
    sign_in(client, user)

    assert client.get("/api/admin/queue").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/analytics/admin").status_code == 403


def test_unapproved_business_cannot_create_listing(client):
    user = make_user("pending-business", role="business", business_approved=False)
    sign_in(client, user)

    response = client.post(
        "/api/business/listings",
        json={"title": "Junior Developer"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    assert backend.BusinessListing.query.count() == 0


def test_non_grad_cannot_submit_alumni_verification(client):
    user = make_user("trade-user", role="trade")
    sign_in(client, user)

    response = client.post(
        "/api/alumni/verify",
        json={"documentRef": "doc-1"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    assert backend.AlumniVerification.query.count() == 0


# ---------------------------------------------------------------------------
# Notification ownership
# ---------------------------------------------------------------------------

def test_notifications_list_contains_only_callers_notifications(client):
    alice = make_user("alice")
    bob = make_user("bob")

    backend.db.session.add_all([
        backend.Notification(user_id=alice.id, type="test", text="alice note"),
        backend.Notification(user_id=bob.id, type="test", text="bob note"),
    ])
    backend.db.session.commit()

    sign_in(client, alice)
    response = client.get("/api/notifications")

    assert response.status_code == 200
    texts = [item["text"] for item in response.json["notifications"]]
    assert texts == ["alice note"]


def test_user_cannot_mark_another_users_notification_read(client):
    alice = make_user("alice")
    bob = make_user("bob")

    note = backend.Notification(
        user_id=bob.id,
        type="test",
        text="private",
        read=False,
    )
    backend.db.session.add(note)
    backend.db.session.commit()

    sign_in(client, alice)
    response = client.post(
        f"/api/notifications/{note.id}/read",
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    backend.db.session.refresh(note)
    assert note.read is False


def test_read_all_only_changes_callers_notifications(client):
    alice = make_user("alice")
    bob = make_user("bob")

    alice_note = backend.Notification(
        user_id=alice.id, type="test", text="alice", read=False
    )
    bob_note = backend.Notification(
        user_id=bob.id, type="test", text="bob", read=False
    )
    backend.db.session.add_all([alice_note, bob_note])
    backend.db.session.commit()

    sign_in(client, alice)
    response = client.post(
        "/api/notifications/read-all",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    backend.db.session.refresh(alice_note)
    backend.db.session.refresh(bob_note)
    assert alice_note.read is True
    assert bob_note.read is False


# ---------------------------------------------------------------------------
# Profile visibility
# ---------------------------------------------------------------------------

def test_hidden_profile_is_not_visible_to_other_regular_user(client):
    owner = make_user("owner", profile_visible=False)
    viewer = make_user("viewer")

    sign_in(client, viewer)
    response = client.get(f"/api/users/{owner.id}")

    assert response.status_code == 404
    assert backend.ProfileView.query.count() == 0


def test_hidden_profile_remains_visible_to_owner(client):
    owner = make_user("owner", profile_visible=False)

    sign_in(client, owner)
    response = client.get(f"/api/users/{owner.id}")

    assert response.status_code == 200
    assert response.json["id"] == owner.id


def test_hidden_profile_remains_visible_to_admin(client):
    owner = make_user("owner", profile_visible=False)
    admin = make_user("admin", role="admin")

    sign_in(client, admin)
    response = client.get(f"/api/users/{owner.id}")

    assert response.status_code == 200
    assert response.json["id"] == owner.id


def test_visible_profile_view_is_recorded_for_other_user(client):
    owner = make_user("owner", profile_visible=True)
    viewer = make_user("viewer")

    sign_in(client, viewer)
    response = client.get(f"/api/users/{owner.id}")

    assert response.status_code == 200
    view = backend.ProfileView.query.one()
    assert view.viewed_user_id == owner.id
    assert view.viewer_user_id == viewer.id


# ---------------------------------------------------------------------------
# Approval actions
# ---------------------------------------------------------------------------

def test_non_admin_cannot_approve_business(client):
    target = make_user("business", role="business", business_approved=False)
    actor = make_user("grad-user", role="grad")

    sign_in(client, actor)
    response = client.post(
        f"/api/admin/users/{target.id}/approve-business",
        headers=csrf_headers(client),
    )

    assert response.status_code == 403
    backend.db.session.refresh(target)
    assert target.business_approved is False


def test_admin_can_approve_business(client):
    target = make_user("business", role="business", business_approved=False)
    admin = make_user("admin", role="admin")

    sign_in(client, admin)
    response = client.post(
        f"/api/admin/users/{target.id}/approve-business",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    backend.db.session.refresh(target)
    assert target.business_approved is True


def test_admin_listing_approval_creates_live_opportunity(client):
    business = make_user("business", role="business", business_approved=True)
    admin = make_user("admin", role="admin")

    queue = backend.ApprovalQueueItem(
        title="Junior Developer",
        co=business.name,
        tags="Python",
        status="pending",
    )
    backend.db.session.add(queue)
    backend.db.session.flush()

    listing = backend.BusinessListing(
        owner_user_id=business.id,
        queue_item_id=queue.id,
        title=queue.title,
        co=queue.co,
        tags=queue.tags,
        status="pending",
    )
    backend.db.session.add(listing)
    backend.db.session.commit()

    sign_in(client, admin)
    response = client.post(
        f"/api/admin/queue/{queue.id}/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    backend.db.session.refresh(listing)
    assert listing.status == "live"

    opportunity = backend.Opportunity.query.one()
    assert opportunity.owner_user_id == business.id
    assert opportunity.listing_id == listing.id
    assert opportunity.title == listing.title


def test_students_only_see_and_apply_to_approved_live_listing_opportunities(client):
    student = make_user("student", role="trade")
    business = make_user("business", role="business", business_approved=True)

    def linked_opportunity(title, listing_status, queue_status):
        queue = backend.ApprovalQueueItem(
            title=title, co=business.name, tags="Python", status=queue_status,
        )
        backend.db.session.add(queue)
        backend.db.session.flush()
        listing = backend.BusinessListing(
            owner_user_id=business.id, queue_item_id=queue.id, title=title,
            co=business.name, tags="Python", status=listing_status,
        )
        backend.db.session.add(listing)
        backend.db.session.flush()
        opportunity = backend.Opportunity(
            title=title, co=business.name, tags="Python", listing_id=listing.id,
        )
        backend.db.session.add(opportunity)
        return opportunity

    pending = linked_opportunity("Pending", "pending", "pending")
    rejected = linked_opportunity("Rejected", "rejected", "rejected")
    mismatched = linked_opportunity("Mismatched", "live", "pending")
    visible = linked_opportunity("Visible", "live", "approved")
    legacy = backend.Opportunity(title="Legacy", co="Forge", tags="Python")
    backend.db.session.add(legacy)
    backend.db.session.commit()

    sign_in(client, student)
    response = client.get("/api/opportunities")

    assert response.status_code == 200
    assert {item["id"] for item in response.json} == {visible.id, legacy.id}

    headers = csrf_headers(client)
    for hidden in (pending, rejected, mismatched):
        assert client.post(f"/api/opportunities/{hidden.id}/apply", headers=headers).status_code == 404
    assert client.post(f"/api/opportunities/{visible.id}/apply", headers=headers).status_code == 200


def test_admin_can_approve_alumni_verification(client):
    graduate = make_user("graduate", role="grad", alumni_verified=False)
    admin = make_user("admin", role="admin")

    record = backend.AlumniVerification(
        user_id=graduate.id,
        document_ref="proof.pdf",
        note="verification",
        status="pending",
    )
    backend.db.session.add(record)
    backend.db.session.commit()

    sign_in(client, admin)
    response = client.post(
        f"/api/admin/alumni-verifications/{record.id}/approve",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    backend.db.session.refresh(record)
    backend.db.session.refresh(graduate)
    assert record.status == "approved"
    assert graduate.alumni_verified is True
