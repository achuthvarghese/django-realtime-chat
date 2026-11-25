import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.urls import reverse

from chat.models import Message, Room
from realtime_chat.asgi import application

User = get_user_model()


@pytest.fixture
def maya(db):
    return User.objects.create_user("maya", password="pw")


@pytest.fixture
def arjun(db):
    return User.objects.create_user("arjun", password="pw")


@pytest.fixture
def room(maya, arjun):
    room = Room.objects.create(name="maya-arjun", type=Room.RoomTypes.PRIVATE)
    room.members.add(maya, arjun)
    return room


@pytest.mark.django_db
class TestChatView:
    def test_requires_login(self, client):
        response = client.get(reverse("chat:chat"))
        assert response.status_code == 302
        assert reverse("account:login") in response.url

    def test_lists_rooms(self, client, maya, room):
        client.force_login(maya)
        response = client.get(reverse("chat:chat"))
        assert response.status_code == 200
        assert room in response.context["rooms"]

    def test_shows_room_messages(self, client, maya, room):
        message = Message.objects.create(content="hello", room=room, user=maya)
        message.visible_for.add(maya)
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.status_code == 200
        assert list(response.context["room_messages"]) == [message]


def make_communicator(room_id, user=None):
    communicator = WebsocketCommunicator(
        application, f"/chat/{room_id}", headers=[(b"origin", b"http://localhost")]
    )
    if user is not None:
        communicator.scope["user"] = user
    return communicator


@pytest.mark.django_db(transaction=True)
class TestChatConsumer:
    async def test_member_message_is_saved_and_broadcast(self, maya, room):
        communicator = make_communicator(room.id, maya)
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({"type": "save_message", "message": "hi"})
        response = await communicator.receive_json_from()

        assert response["type"] == "save_message"
        assert response["message"] == "hi"
        assert response["user"] == "maya"
        count = await database_sync_to_async(Message.objects.filter(room=room).count)()
        assert count == 1
        await communicator.disconnect()

    async def test_unknown_room_is_reported(self, maya):
        communicator = make_communicator("00000000-0000-0000-0000-000000000000", maya)
        connected, _ = await communicator.connect()
        assert connected
        response = await communicator.receive_json_from()
        assert response["code"] == 404
        await communicator.disconnect()


@pytest.mark.django_db
class TestChatViewAccess:
    def test_non_member_gets_404(self, client, room):
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.status_code == 404

    def test_malformed_room_id_gets_404(self, client, maya):
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": "not-a-uuid"})
        assert response.status_code == 404

    def test_room_title_is_escaped(self, client, maya, arjun, room):
        arjun.first_name = "<script>alert(1)</script>"
        arjun.save()
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert b"<script>alert(1)</script>" not in response.content
        assert b"&lt;script&gt;" in response.content

    def test_private_room_without_other_member_uses_name(self, client, maya):
        solo = Room.objects.create(name="notes", type=Room.RoomTypes.PRIVATE)
        solo.members.add(maya)
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": solo.id})
        assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
class TestChatConsumerSecurity:
    async def test_anonymous_user_is_refused(self, room):
        from django.contrib.auth.models import AnonymousUser

        communicator = make_communicator(room.id, AnonymousUser())
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4401

    async def test_non_member_is_refused(self, room):
        outsider = await database_sync_to_async(User.objects.create_user)(
            "eve", password="pw"
        )
        communicator = make_communicator(room.id, outsider)
        await communicator.connect()
        response = await communicator.receive_json_from()
        assert (response["type"], response["code"]) == ("error", 403)
        assert (await communicator.receive_output())["code"] == 4403

    async def test_malformed_room_id_is_not_found(self, maya):
        communicator = make_communicator("not-a-uuid", maya)
        await communicator.connect()
        response = await communicator.receive_json_from()
        assert response["code"] == 404

    async def test_invalid_json_returns_error(self, maya, room):
        communicator = make_communicator(room.id, maya)
        await communicator.connect()
        await communicator.send_to(text_data="{not json")
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        await communicator.disconnect()

    async def test_empty_message_is_not_saved(self, maya, room):
        communicator = make_communicator(room.id, maya)
        await communicator.connect()
        await communicator.send_json_to({"type": "save_message", "message": "   "})
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        await communicator.send_json_to({"type": "save_message"})
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        count = await database_sync_to_async(Message.objects.count)()
        assert count == 0
        await communicator.disconnect()

    async def test_overlong_message_is_rejected(self, maya, room):
        communicator = make_communicator(room.id, maya)
        await communicator.connect()
        await communicator.send_json_to({"type": "save_message", "message": "x" * 4001})
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        await communicator.disconnect()

    async def test_errors_go_only_to_sender(self, maya, arjun, room):
        sender = make_communicator(room.id, maya)
        other = make_communicator(room.id, arjun)
        await sender.connect()
        await other.connect()
        await sender.send_json_to({"type": "drop_tables"})
        assert (await sender.receive_json_from())["type"] == "error"
        assert await other.receive_nothing()
        await sender.disconnect()
        await other.disconnect()

    async def test_messages_reach_other_members(self, maya, arjun, room):
        sender = make_communicator(room.id, maya)
        other = make_communicator(room.id, arjun)
        await sender.connect()
        await other.connect()
        await sender.send_json_to({"type": "save_message", "message": "<b>hi</b>"})
        response = await other.receive_json_from()
        assert response["message"] == "<b>hi</b>"
        assert response["user"] == "maya"
        await sender.disconnect()
        await other.disconnect()

    async def test_clear_room_hides_messages_for_requester_only(
        self, maya, arjun, room
    ):
        sender = make_communicator(room.id, maya)
        other = make_communicator(room.id, arjun)
        await sender.connect()
        await other.connect()
        await sender.send_json_to({"type": "save_message", "message": "hello"})
        await sender.receive_json_from()
        await other.receive_json_from()

        await sender.send_json_to({"type": "clear_room"})
        response = await sender.receive_json_from()
        assert response["type"] == "clear_room"
        assert await other.receive_nothing()

        visible_to_maya = await database_sync_to_async(
            Message.objects.filter(visible_for=maya).count
        )()
        visible_to_arjun = await database_sync_to_async(
            Message.objects.filter(visible_for=arjun).count
        )()
        assert (visible_to_maya, visible_to_arjun) == (0, 1)
        await sender.disconnect()
        await other.disconnect()
