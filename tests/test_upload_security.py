"""T-102 video upload boundary, validation and serving regressions."""

from io import BytesIO
import os

from werkzeug.security import generate_password_hash

import forge_backend as backend


MP4_HEADER = (
    b"\x00\x00\x00\x18"
    b"ftyp"
    b"isom"
    b"\x00\x00\x02\x00"
    b"isomiso2"
)


def make_user(username="alice", role="trade"):
    user = backend.User(
        username=username,
        name=username,
        role=role,
        password_hash=generate_password_hash("password123"),
    )
    backend.db.session.add(user)
    backend.db.session.commit()
    return user


def sign_in(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user.id


def headers(client):
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return {
        "Origin": "http://localhost",
        "X-CSRF-Token": response.json["csrfToken"],
    }


def upload(client, raw, filename="clip.mp4"):
    return client.post(
        "/api/posts/video",
        data={"video": (BytesIO(raw), filename), "caption": "test"},
        headers=headers(client),
    )


def test_video_upload_requires_authentication(client):
    response = client.post(
        "/api/posts/video",
        data={"video": (BytesIO(MP4_HEADER), "clip.mp4")},
    )
    assert response.status_code == 401


def test_video_upload_rejects_non_student_role(client):
    user = make_user(role="business")
    sign_in(client, user)

    response = upload(client, MP4_HEADER)

    assert response.status_code == 403
    assert backend.Post.query.count() == 0


def test_video_upload_rejects_unsupported_extension(client):
    user = make_user()
    sign_in(client, user)

    response = upload(client, MP4_HEADER, "clip.exe")

    assert response.status_code == 400
    assert backend.Post.query.count() == 0


def test_video_upload_rejects_fake_content(client):
    user = make_user()
    sign_in(client, user)

    response = upload(client, b"this is not a video", "clip.mp4")

    assert response.status_code == 415
    assert backend.Post.query.count() == 0
    assert os.listdir(backend.UPLOAD_DIR) == []


def test_video_upload_rejects_container_extension_mismatch(client):
    user = make_user()
    sign_in(client, user)

    response = upload(client, MP4_HEADER, "clip.avi")

    assert response.status_code == 415
    assert backend.Post.query.count() == 0


def test_request_size_preflight_runs_before_multipart_processing(
    client, monkeypatch
):
    user = make_user()
    sign_in(client, user)

    # Multipart framing alone is larger than this threshold.
    monkeypatch.setattr(backend, "MAX_VIDEO_REQUEST_BYTES", 64)

    response = upload(client, MP4_HEADER)

    assert response.status_code == 413
    assert backend.Post.query.count() == 0
    assert os.listdir(backend.UPLOAD_DIR) == []


def test_bounded_stream_rejects_oversized_file_and_cleans_partial(
    client, monkeypatch
):
    user = make_user()
    sign_in(client, user)

    monkeypatch.setattr(backend, "MAX_VIDEO_BYTES", len(MP4_HEADER) + 4)
    monkeypatch.setattr(backend, "MAX_VIDEO_REQUEST_BYTES", 4096)

    response = upload(client, MP4_HEADER + b"x" * 32)

    assert response.status_code == 413
    assert backend.Post.query.count() == 0
    assert os.listdir(backend.UPLOAD_DIR) == []


def test_valid_signature_upload_is_stored_when_ffmpeg_is_unavailable(
    client, monkeypatch
):
    user = make_user()
    sign_in(client, user)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)

    response = upload(client, MP4_HEADER + b"payload")

    assert response.status_code == 201
    post = backend.Post.query.one()
    assert post.media is True

    video_name = os.path.basename(post.video_url)
    thumb_name = os.path.basename(post.thumb_url)
    assert os.path.isfile(os.path.join(backend.UPLOAD_DIR, video_name))
    assert os.path.isfile(os.path.join(backend.UPLOAD_DIR, thumb_name))


def test_upload_files_are_not_public_and_inherit_feed_authorization(
    app, client, monkeypatch
):
    owner = make_user("owner", role="trade")
    sign_in(client, owner)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)

    response = upload(client, MP4_HEADER + b"payload")
    assert response.status_code == 201
    video_url = response.json["videoUrl"]

    anonymous = app.test_client()
    assert anonymous.get(video_url).status_code == 401

    grad = make_user("grad-user", role="grad")
    other_role = app.test_client()
    sign_in(other_role, grad)
    assert other_role.get(video_url).status_code == 404

    peer = make_user("trade-peer", role="trade")
    same_role = app.test_client()
    sign_in(same_role, peer)
    assert same_role.get(video_url).status_code == 200

    admin = make_user("admin", role="admin")
    moderator = app.test_client()
    sign_in(moderator, admin)
    assert moderator.get(video_url).status_code == 200


def test_orphan_and_removed_media_are_not_served(
    app, client, monkeypatch
):
    owner = make_user("owner", role="trade")
    sign_in(client, owner)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)

    response = upload(client, MP4_HEADER + b"payload")
    assert response.status_code == 201

    post = backend.Post.query.one()
    video_url = post.video_url

    orphan_name = "unreferenced.mp4"
    with open(os.path.join(backend.UPLOAD_DIR, orphan_name), "wb") as fh:
        fh.write(MP4_HEADER)
    assert client.get(f"/uploads/{orphan_name}").status_code == 404

    post.removed = True
    backend.db.session.commit()

    # Soft removal immediately revokes access. T-102 deliberately does not
    # physically delete bytes because irreversible retention cleanup requires
    # a separately approved policy.
    assert client.get(video_url).status_code == 404
    assert os.path.isfile(
        os.path.join(backend.UPLOAD_DIR, os.path.basename(video_url))
    )
