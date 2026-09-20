"""Realtime fan-out: hub routing, event publication and the notification socket."""
import json

import pytest
from litestar.testing import AsyncTestClient

from app.main import app
from app.services import events
from app.services.events import Event
from app.services.websocket_hub import ConnectionInfo, hub


class FakeSocket:
    """Records what the hub would have written to a real WebSocket."""

    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    async def send_text(self, data: str) -> None:
        if self.fail:
            raise RuntimeError("socket is gone")
        self.sent.append(json.loads(data))


def make_conn(user_id: int, role: str, scope: str = "user", ticket_id=None, fail: bool = False) -> ConnectionInfo:
    return ConnectionInfo(
        socket=FakeSocket(fail=fail),  # type: ignore[arg-type]
        user_id=user_id,
        user_name=f"user{user_id}",
        role=role,
        ticket_id=ticket_id,
        scope=scope,
    )


@pytest.fixture(autouse=True)
def clean_hub():
    hub.reset()
    yield
    hub.reset()


@pytest.mark.asyncio
async def test_staff_room_receives_queue_events():
    agent = make_conn(2, "agent")
    customer = make_conn(3, "customer")
    await hub.connect(agent)
    await hub.connect(customer)

    await events.publish(Event(type="ticket_created", notification={"ticket_id": 7}, staff=True))

    assert [m["type"] for m in agent.socket.sent] == ["ticket_created"]
    # A customer is not on the staff channel.
    assert customer.socket.sent == []


@pytest.mark.asyncio
async def test_admin_room_is_restricted_to_admins():
    agent = make_conn(2, "agent")
    admin = make_conn(1, "admin")
    await hub.connect(agent)
    await hub.connect(admin)

    await events.publish(Event(type="catalog_changed", notification={"resource": "faq"}, admins=True))

    assert len(admin.socket.sent) == 1
    assert agent.socket.sent == []


@pytest.mark.asyncio
async def test_direct_user_events_reach_only_that_user():
    first = make_conn(10, "customer")
    second = make_conn(11, "customer")
    await hub.connect(first)
    await hub.connect(second)

    await events.publish(Event(type="ticket_updated", notification={"ticket_id": 1}, user_ids=[10]))

    assert len(first.socket.sent) == 1
    assert second.socket.sent == []


@pytest.mark.asyncio
async def test_whispers_never_reach_customers():
    customer = make_conn(10, "customer")
    agent = make_conn(11, "agent")
    await hub.connect(customer)
    await hub.connect(agent)

    await events.publish(
        Event(
            type="message_created",
            notification={"ticket_id": 1, "message_type": "whisper"},
            ticket_payload={"type": "new_message", "message": {"content": "internal"}},
            ticket_id=1,
            user_ids=[10, 11],
            staff=True,
            whisper=True,
        )
    )

    assert customer.socket.sent == []
    assert len(agent.socket.sent) == 1


@pytest.mark.asyncio
async def test_ticket_room_gets_the_full_payload():
    viewer = make_conn(10, "customer", scope="ticket", ticket_id=5)
    await hub.connect(viewer)

    await events.publish(
        Event(
            type="message_created",
            notification={"ticket_id": 5, "preview": "hi"},
            ticket_payload={"type": "new_message", "message": {"id": 1, "content": "full body"}},
            ticket_id=5,
        )
    )

    assert viewer.socket.sent[0]["message"]["content"] == "full body"


@pytest.mark.asyncio
async def test_dead_connections_are_dropped():
    dead = make_conn(10, "customer", fail=True)
    await hub.connect(dead)
    assert hub.connection_count() == 1

    await events.publish(Event(type="ticket_updated", notification={}, user_ids=[10]))

    # The failed send must not leave the connection registered forever.
    assert hub.connection_count() == 0


@pytest.mark.asyncio
async def test_an_agent_is_not_notified_twice_for_the_same_event():
    """An agent is in both their user room and the staff room; the event must
    still be delivered exactly once."""
    agent = make_conn(2, "agent")
    await hub.connect(agent)

    await events.publish(
        Event(
            type="message_created",
            notification={"ticket_id": 1},
            ticket_id=1,
            user_ids=[2],
            staff=True,
        )
    )

    assert len(agent.socket.sent) == 1



@pytest.mark.asyncio
async def test_disconnect_removes_every_room():
    conn = make_conn(10, "admin")
    await hub.connect(conn)
    assert hub.connection_count() == 1
    await hub.disconnect(conn)
    assert hub.connection_count() == 0


@pytest.mark.asyncio
async def test_http_mutations_publish_events(monkeypatch):
    """Creating a ticket must publish a realtime event, not just write to the DB."""
    published: list[Event] = []
    original = events.publish

    async def recorder(event: Event) -> None:
        published.append(event)
        await original(event)

    monkeypatch.setattr(events, "publish", recorder)

    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "root@test.com",
                "username": "root_admin",
                "full_name": "Root Admin",
                "password": "rootpass123",
            },
        )
        admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "rt@test.com",
                "username": "rt_user",
                "full_name": "RT User",
                "password": "customerpass123",
            },
        )
        customer_headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Realtime please", "description": "Notify the staff."},
                headers=customer_headers,
            )
        ).json()
        ticket_id = ticket["id"]

        await client.post(
            f"/api/tickets/{ticket_id}/messages", json={"content": "any update?"}, headers=customer_headers
        )
        await client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "resolved"}, headers=admin_headers
        )
        await client.patch(
            f"/api/users/{customer.json()['user']['id']}/role", json={"role": "agent"}, headers=admin_headers
        )

        types = [event.type for event in published]

    assert "ticket_created" in types
    assert "message_created" in types
    assert "ticket_updated" in types
    assert "user_updated" in types


@pytest.mark.asyncio
async def test_a_status_change_reaches_the_open_conversation_with_its_action_card():
    """The reported bug: the chat view only appends messages it receives, so a
    status change written as an action card stayed invisible until a reload.

    The viewer is a real connection in the ticket room; the mutation goes through
    the HTTP API, so this covers the whole path from `PATCH /status` to the frame.
    """
    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "admin@realtimetest.com",
                "username": "rt_admin",
                "full_name": "RT Admin",
                "password": "adminpass123",
            },
        )
        admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "viewer@realtimetest.com",
                "username": "rt_viewer",
                "full_name": "RT Viewer",
                "password": "customerpass123",
            },
        )
        customer_body = customer.json()
        customer_headers = {"Authorization": f"Bearer {customer_body['access_token']}"}

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Status please", "description": "I want to see it live."},
                headers=customer_headers,
            )
        ).json()

        viewer = make_conn(
            customer_body["user"]["id"], "customer", scope="ticket", ticket_id=ticket["id"]
        )
        await hub.connect(viewer)

        await client.patch(
            f"/api/tickets/{ticket['id']}/status", json={"status": "resolved"}, headers=admin_headers
        )

        frames = [frame for frame in viewer.socket.sent if frame["type"] == "ticket_updated"]
        assert len(frames) == 1, viewer.socket.sent

        frame = frames[0]
        assert frame["ticket"]["status"] == "resolved"

        card = frame["message"]
        assert card["message_type"] == "action_card"
        assert card["sender_role"] == "system"
        assert "resolved" in card["content"]
        assert card["id"]

        # It is the same row the conversation endpoint returns, so the live view
        # and a reload cannot disagree.
        page = (
            await client.get(f"/api/tickets/{ticket['id']}/messages", headers=admin_headers)
        ).json()
        assert any(message["id"] == card["id"] for message in page["items"])


@pytest.mark.asyncio
async def test_priority_and_assignment_changes_carry_their_action_cards():
    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "admin@realtimetest.com",
                "username": "rt_admin",
                "full_name": "RT Admin",
                "password": "adminpass123",
            },
        )
        admin_body = admin.json()
        admin_headers = {"Authorization": f"Bearer {admin_body['access_token']}"}

        customer = await client.post(
            "/api/auth/register",
            json={
                "email": "viewer@realtimetest.com",
                "username": "rt_viewer",
                "full_name": "RT Viewer",
                "password": "customerpass123",
            },
        )
        customer_headers = {"Authorization": f"Bearer {customer.json()['access_token']}"}

        ticket = (
            await client.post(
                "/api/tickets",
                json={"title": "Priority please", "description": "I want to see it live."},
                headers=customer_headers,
            )
        ).json()

        viewer = make_conn(admin_body["user"]["id"], "admin", scope="ticket", ticket_id=ticket["id"])
        await hub.connect(viewer)

        await client.patch(
            f"/api/tickets/{ticket['id']}/priority", json={"priority": "urgent"}, headers=admin_headers
        )
        await client.patch(
            f"/api/tickets/{ticket['id']}/assign",
            json={"agent_id": admin_body["user"]["id"]},
            headers=admin_headers,
        )

        cards = [
            frame["message"]["content"]
            for frame in viewer.socket.sent
            if frame["type"] == "ticket_updated"
        ]
        assert len(cards) == 2, viewer.socket.sent
        assert "URGENT" in cards[0]
        assert "assigned to RT Admin" in cards[1]


@pytest.mark.asyncio
async def test_notification_socket_requires_a_token():
    async with AsyncTestClient(app=app) as client:
        ws = await client.websocket_connect("/ws/notifications")
        # The handler accepts then closes with 4401; no frame is delivered.
        with pytest.raises(Exception):
            with ws:
                ws.receive_json()


@pytest.mark.asyncio
async def test_notification_socket_reports_its_channels():
    async with AsyncTestClient(app=app) as client:
        admin = await client.post(
            "/api/auth/setup-admin",
            json={
                "email": "root@test.com",
                "username": "root_admin",
                "full_name": "Root Admin",
                "password": "rootpass123",
            },
        )
        token = admin.json()["access_token"]

        ws = await client.websocket_connect(f"/ws/notifications?token={token}")
        with ws:
            ready = ws.receive_json()

    assert ready["type"] == "ready"
    assert ready["role"] == "admin"
    assert set(ready["channels"]) == {"user", "staff", "admin"}
