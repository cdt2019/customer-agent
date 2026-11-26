"""买家发图片（docs/09）：只收图片、去掉元数据、缩小、限数量、别人看不到、到期连文件一起删。"""

import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image as Pil
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from customer_agent import retention, settings
from customer_agent.api import chats, conversations, deps
from customer_agent.chat import images
from customer_agent.db import Base, ChatMessage, Conversation, Image, IndexVersion, KnowledgeBase

KEY = {"X-Api-Key": "k"}


def picture(kind: str = "JPEG", size: tuple[int, int] = (64, 48), exif: bool = False) -> bytes:
    out = io.BytesIO()
    image = Pil.new("RGB", size, (200, 30, 30))
    extra = {}
    if exif:
        data = Pil.Exif()
        data[0x010F] = "SpyCam"  # 相机厂商
        data.get_ifd(0x8825)[2] = (31.0, 14.0, 0.0)  # GPS 纬度
        extra["exif"] = data
    image.save(out, format=kind, **extra)
    return out.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(settings, "SERVICE_API_KEY", "k")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    for module in (chats, conversations):
        app.include_router(module.router)

    def db():
        with Session() as session:
            yield session

    app.dependency_overrides[deps.db] = db
    with Session() as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        session.add(index)
        session.flush()
        # 客服在接：发图不调模型，测试不用替身
        session.add_all([
            Conversation(id="c1", kb_id=kb.id, index_id=index.id, visitor_id="v", status="staff", staff_at=datetime.now(UTC)),
            Conversation(id="c2", kb_id=kb.id, index_id=index.id, visitor_id="w"),
        ])
        session.commit()
    return TestClient(app), Session, tmp_path


def test_clean_strips_metadata_and_shrinks(world):
    cleaned = images.clean(picture(exif=True))
    stored = Pil.open(settings.IMAGES_DIR / cleaned.stored_name)
    assert cleaned.stored_name.endswith(".jpg") and not stored.getexif()
    big = images.clean(picture("PNG", (4000, 1000)))
    assert (big.width, big.height) == (2048, 512) and big.stored_name.endswith(".png")


@pytest.mark.parametrize("data", [b"not an image", picture("GIF"), b"\x89PNG\r\n\x1a\n" + b"0" * 100])
def test_clean_rejects_what_is_not_a_supported_picture(world, data):
    with pytest.raises(images.Rejected):
        images.clean(data)


def test_clean_rejects_too_big(world):
    with pytest.raises(images.Rejected, match="5MB"):
        images.clean(b"0" * (images.MAX_BYTES + 1))


def send(client, conversation="c1", data=None):
    return client.post(f"/v1/conversations/{conversation}/images", files={"file": ("a.jpg", data or picture(), "image/jpeg")}, headers=KEY)


def test_upload_attaches_to_a_message_and_only_its_owner_conversation_sees_it(world):
    client, Session, _ = world
    reply = send(client)
    user = json.loads(reply.text.split("\n")[1][6:])
    assert user["text"] == images.TEXT and user["image"]["width"] == 64
    image_id = user["image"]["id"]

    history = client.get("/v1/conversations/c1", headers=KEY).json()["messages"]
    assert history[-1]["image"]["id"] == image_id
    own = client.get(f"/v1/conversations/c1/images/{image_id}", headers=KEY)
    assert own.headers["content-type"] == "image/jpeg" and own.headers["content-security-policy"] == "sandbox"
    assert client.get(f"/v1/conversations/c2/images/{image_id}", headers=KEY).status_code == 404
    assert client.get(f"/api/chats/images/{image_id}").status_code == 200
    assert client.get("/api/chats/c1").json()["messages"][-1]["image"]["id"] == image_id
    assert send(client, data=b"<script>").status_code == 422


def test_at_most_five_pictures_per_conversation(world):
    client, *_ = world
    for _ in range(images.PER_CONVERSATION):
        assert send(client).status_code == 200
    assert send(client).status_code == 429


def test_retention_removes_the_files(world):
    client, Session, folder = world
    send(client)
    with Session() as session:
        stored = session.scalars(select(Image.stored_name)).one()
        session.get(Conversation, "c1").created_at = datetime.now(UTC) - timedelta(days=100)
        session.commit()
        assert (folder / stored).exists()
        retention.clean(session)
        assert not (folder / stored).exists() and session.scalars(select(ChatMessage)).first() is None
