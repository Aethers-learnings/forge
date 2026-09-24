"""Profile-image validation, storage, authorization and lifecycle regressions."""

from io import BytesIO
import os

from PIL import Image
from werkzeug.security import generate_password_hash

import forge_backend as backend


def make_user(username="photo-user", role="grad"):
    user = backend.User(
        username=username,
        name=username,
        role=role,
        password_hash=generate_password_hash("password123"),
    )
    backend.db.session.add(user)
    backend.db.session.commit()
    return user.id


def sign_in(client, uid):
    with client.session_transaction() as session:
        session["user_id"] = uid


def csrf_headers(client):
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return {
        "X-CSRF-Token": response.json["csrfToken"],
        "Origin": "http://localhost",
    }


def image_bytes(fmt="PNG", size=(80, 80), color=(40, 110, 98)):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format=fmt)
    return output.getvalue()


def upload_data(raw=None, filename="avatar.png", mimetype="image/png"):
    return {
        "image": (
            BytesIO(raw if raw is not None else image_bytes()),
            filename,
            mimetype,
        )
    }


def test_profile_image_requires_authentication(client):
    response = client.post("/api/profile/image", data=upload_data())

    assert response.status_code == 401
    assert backend.ProfileImage.query.count() == 0


def test_profile_image_requires_csrf(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.post("/api/profile/image", data=upload_data())

    assert response.status_code == 403
    assert response.json["code"] == "csrf_failed"
    assert backend.ProfileImage.query.count() == 0


def test_valid_profile_image_is_canonicalized_stored_and_exposed(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.post(
        "/api/profile/image",
        data=upload_data(),
        headers=csrf_headers(client),
    )

    assert response.status_code == 201

    avatar_url = response.json["avatarUrl"]
    assert avatar_url.startswith("/profile-images/profile_")
    assert avatar_url.endswith(".jpg")

    record = backend.ProfileImage.query.filter_by(user_id=uid).one()
    stored_path = os.path.join(backend.PROFILE_IMAGE_DIR, record.filename)

    assert os.path.isfile(stored_path)

    with Image.open(stored_path) as stored:
        assert stored.format == "JPEG"
        assert stored.size == backend.PROFILE_IMAGE_SIZE

    served = client.get(avatar_url)
    assert served.status_code == 200
    assert served.mimetype == "image/jpeg"

    profile = client.get(f"/api/users/{uid}")
    assert profile.status_code == 200
    assert profile.json["avatarUrl"] == avatar_url


def test_business_account_can_use_same_profile_image_pipeline(client):
    uid = make_user(username="business-photo", role="business")
    sign_in(client, uid)

    response = client.post(
        "/api/profile/image",
        data=upload_data(),
        headers=csrf_headers(client),
    )

    assert response.status_code == 201
    assert response.json["avatarUrl"].startswith("/profile-images/profile_")


def test_rejects_unsupported_mime_type(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.post(
        "/api/profile/image",
        data=upload_data(mimetype="text/plain"),
        headers=csrf_headers(client),
    )

    assert response.status_code == 415
    assert backend.ProfileImage.query.count() == 0


def test_rejects_fake_image_content(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.post(
        "/api/profile/image",
        data=upload_data(raw=b"this is not an image"),
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert backend.ProfileImage.query.count() == 0


def test_mime_must_match_actual_image_format(client):
    uid = make_user()
    sign_in(client, uid)

    jpeg = image_bytes(fmt="JPEG")

    response = client.post(
        "/api/profile/image",
        data=upload_data(
            raw=jpeg,
            filename="pretending-to-be-png.png",
            mimetype="image/png",
        ),
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert backend.ProfileImage.query.count() == 0


def test_oversized_profile_image_is_rejected(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.post(
        "/api/profile/image",
        data=upload_data(
            raw=b"x" * (backend.MAX_PROFILE_IMAGE_BYTES + 1),
        ),
        headers=csrf_headers(client),
    )

    assert response.status_code == 413
    assert backend.ProfileImage.query.count() == 0


def test_replacing_image_removes_previous_file(client):
    uid = make_user()
    sign_in(client, uid)

    first = client.post(
        "/api/profile/image",
        data=upload_data(),
        headers=csrf_headers(client),
    )

    assert first.status_code == 201

    first_record = backend.ProfileImage.query.filter_by(user_id=uid).one()
    first_filename = first_record.filename
    first_path = os.path.join(backend.PROFILE_IMAGE_DIR, first_filename)

    assert os.path.exists(first_path)

    second = client.post(
        "/api/profile/image",
        data=upload_data(
            raw=image_bytes(color=(181, 67, 43)),
            filename="replacement.png",
        ),
        headers=csrf_headers(client),
    )

    assert second.status_code == 201

    backend.db.session.expire_all()

    second_record = backend.ProfileImage.query.filter_by(user_id=uid).one()

    assert second_record.filename != first_filename
    assert not os.path.exists(first_path)
    assert os.path.exists(
        os.path.join(backend.PROFILE_IMAGE_DIR, second_record.filename)
    )


def test_remove_image_deletes_record_file_and_payload_reference(client):
    uid = make_user()
    sign_in(client, uid)

    uploaded = client.post(
        "/api/profile/image",
        data=upload_data(),
        headers=csrf_headers(client),
    )

    assert uploaded.status_code == 201

    record = backend.ProfileImage.query.filter_by(user_id=uid).one()
    path = os.path.join(backend.PROFILE_IMAGE_DIR, record.filename)

    assert os.path.exists(path)

    # Unsafe deletion must still pass through the global CSRF guard.
    blocked = client.delete("/api/profile/image")
    assert blocked.status_code == 403

    response = client.delete(
        "/api/profile/image",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json["avatarUrl"] == ""
    assert backend.ProfileImage.query.filter_by(user_id=uid).first() is None
    assert not os.path.exists(path)


def test_remove_missing_image_is_idempotent(client):
    uid = make_user()
    sign_in(client, uid)

    response = client.delete(
        "/api/profile/image",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json["avatarUrl"] == ""


def test_hidden_profile_image_not_served_to_other_users(client, app):
    owner_id = make_user("hidden-owner")
    viewer_id = make_user("viewer")

    sign_in(client, owner_id)

    uploaded = client.post(
        "/api/profile/image",
        data=upload_data(),
        headers=csrf_headers(client),
    )

    assert uploaded.status_code == 201
    avatar_url = uploaded.json["avatarUrl"]

    owner = backend.db.session.get(backend.User, owner_id)
    owner.profile_visible = False
    backend.db.session.commit()

    other = app.test_client()
    sign_in(other, viewer_id)

    assert other.get(avatar_url).status_code == 404
    assert client.get(avatar_url).status_code == 200


def test_profile_image_route_rejects_unknown_filename(client):
    uid = make_user()
    sign_in(client, uid)

    assert client.get("/profile-images/not-a-forge-image.jpg").status_code == 404
