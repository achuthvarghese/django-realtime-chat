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
        assert [r["id"] for r in response.context["rooms"]] == [str(room.id)]

    def test_shows_room_messages(self, client, maya, room):
        message = Message.objects.create(content="hello", room=room, user=maya)
        message.visible_for.add(maya)
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.status_code == 200
        assert [m["id"] for m in response.context["room_messages"]] == [str(message.id)]


def make_messages(room, user, count):
    """`count` messages m0..m{count-1}, one second apart, visible to members."""
    from datetime import timedelta

    from django.utils import timezone

    start = timezone.now() - timedelta(seconds=count)
    members = list(room.members.all())
    created = []
    for i in range(count):
        m = Message.objects.create(content=f"m{i}", room=room, user=user)
        Message.objects.filter(pk=m.pk).update(created_at=start + timedelta(seconds=i))
        m.visible_for.add(*members)
        m.refresh_from_db()
        created.append(m)
    return created


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


class TestInitials:
    @pytest.mark.parametrize(
        "name, expected",
        [("Maya Rao", "MR"), ("maya", "MA"), ("@ops", "OP"), ("", "?"), ("a", "A")],
    )
    def test_initials(self, name, expected):
        from chat.presenters import initials

        assert initials(name) == expected


@pytest.mark.django_db
class TestChatScreen:
    def test_page_uses_design_system(self, client, maya, room):
        client.force_login(maya)
        html = client.get(reverse("chat:chat"), {"room": room.id}).content.decode()
        assert "data-palette=" in html
        assert "bootstrap" not in html.lower()
        assert "moment" not in html.lower()
        assert 'id="initial-messages"' in html
        assert 'id="clear-dialog"' in html

    def test_rooms_ordered_by_latest_message(self, client, maya, arjun, room):
        quiet = Room.objects.create(name="quiet", type=Room.RoomTypes.GROUP)
        quiet.members.add(maya)
        busy = Room.objects.create(name="busy", type=Room.RoomTypes.GROUP)
        busy.members.add(maya)
        message = Message.objects.create(content="latest", room=busy, user=arjun)
        message.visible_for.add(maya)
        client.force_login(maya)
        rooms = client.get(reverse("chat:chat")).context["rooms"]
        assert rooms[0]["title"] == "busy"
        assert rooms[0]["last_content"] == "latest"
        assert rooms[0]["last_is_mine"] is False

    def test_preview_skips_cleared_messages(self, client, maya, arjun, room):
        hidden = Message.objects.create(content="secret", room=room, user=arjun)
        hidden.visible_for.add(arjun)  # cleared by maya
        client.force_login(maya)
        rooms = client.get(reverse("chat:chat")).context["rooms"]
        assert rooms[0]["last_content"] == ""

    def test_private_room_title_is_other_member(self, client, maya, arjun, room):
        arjun.first_name, arjun.last_name = "Arjun", "Kumar"
        arjun.save()
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.context["room_summary"]["title"] == "Arjun Kumar"
        assert response.context["room_summary"]["initials"] == "AK"

    def test_history_is_limited_and_in_order(self, client, maya, room):
        from chat.views import PAGE_SIZE

        make_messages(room, maya, PAGE_SIZE + 5)
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        messages = response.context["room_messages"]
        assert len(messages) == PAGE_SIZE
        assert messages[-1]["message"] == f"m{PAGE_SIZE + 4}"
        assert response.context["history"]["has_more"] is True

    def test_message_text_cannot_break_out_of_json(self, client, maya, room):
        m = Message.objects.create(content="</script><b>x</b>", room=room, user=maya)
        m.visible_for.add(maya)
        client.force_login(maya)
        html = client.get(reverse("chat:chat"), {"room": room.id}).content.decode()
        assert "</script><b>x</b>" not in html

    def test_welcome_without_room(self, client, maya):
        client.force_login(maya)
        html = client.get(reverse("chat:chat")).content.decode()
        assert "You&#x27;re not in any chats yet" in html or "not in any chats" in html


@pytest.mark.django_db(transaction=True)
class TestBroadcastShape:
    async def test_broadcast_includes_display_name_and_initials(self, maya, room):
        maya.first_name, maya.last_name = "Maya", "Rao"
        await database_sync_to_async(maya.save)()
        communicator = make_communicator(room.id, maya)
        await communicator.connect()
        await communicator.send_json_to({"type": "save_message", "message": "hi"})
        response = await communicator.receive_json_from()
        assert response["name"] == "Maya Rao"
        assert response["initials"] == "MR"
        await communicator.disconnect()


@pytest.mark.django_db
class TestPeopleSearch:
    def test_requires_login(self, client):
        assert client.get(reverse("chat:people"), {"q": "a"}).status_code == 302

    def test_matches_username_and_names(self, client, maya, arjun):
        arjun.first_name, arjun.last_name = "Arjun", "Kumar"
        arjun.save()
        client.force_login(maya)
        for query in ("arj", "@arjun", "Kumar", "arjun kum"):
            results = client.get(reverse("chat:people"), {"q": query}).json()["results"]
            assert [r["username"] for r in results] == ["arjun"], query
        assert results[0]["name"] == "Arjun Kumar"
        assert results[0]["initials"] == "AK"

    def test_excludes_self_inactive_and_blank(self, client, maya, arjun):
        arjun.is_active = False
        arjun.save()
        client.force_login(maya)
        assert client.get(reverse("chat:people"), {"q": "a"}).json()["results"] == []
        assert client.get(reverse("chat:people"), {"q": " "}).json()["results"] == []

    def test_post_not_allowed(self, client, maya):
        client.force_login(maya)
        assert client.post(reverse("chat:people")).status_code == 405


@pytest.mark.django_db
class TestStartDirect:
    def test_creates_room_and_redirects(self, client, maya, arjun):
        client.force_login(maya)
        response = client.post(reverse("chat:start_direct"), {"username": "arjun"})
        room = Room.objects.get(type=Room.RoomTypes.PRIVATE)
        assert set(room.members.values_list("username", flat=True)) == {"maya", "arjun"}
        assert response.url == f"/chat/?room={room.id}"

    def test_reuses_existing_room(self, client, maya, arjun, room):
        client.force_login(maya)
        response = client.post(reverse("chat:start_direct"), {"username": "arjun"})
        assert Room.objects.count() == 1
        assert response.url == f"/chat/?room={room.id}"

    def test_group_with_same_people_is_not_reused(self, client, maya, arjun):
        group = Room.objects.create(name="pair", type=Room.RoomTypes.GROUP)
        group.members.add(maya, arjun)
        client.force_login(maya)
        client.post(reverse("chat:start_direct"), {"username": "arjun"})
        assert Room.objects.filter(type=Room.RoomTypes.PRIVATE).count() == 1

    def test_larger_private_room_is_not_reused(self, client, maya, arjun):
        crowd = Room.objects.create(name="crowd", type=Room.RoomTypes.PRIVATE)
        crowd.members.add(maya, arjun, User.objects.create_user("ops", password="pw"))
        client.force_login(maya)
        response = client.post(reverse("chat:start_direct"), {"username": "arjun"})
        assert Room.objects.filter(type=Room.RoomTypes.PRIVATE).count() == 2
        assert str(crowd.id) not in response.url

    def test_cannot_message_self(self, client, maya):
        client.force_login(maya)
        response = client.post(
            reverse("chat:start_direct"), {"username": "maya"}, follow=True
        )
        assert Room.objects.count() == 0
        assert "with yourself" in response.content.decode()

    def test_unknown_user_is_404(self, client, maya):
        client.force_login(maya)
        response = client.post(reverse("chat:start_direct"), {"username": "ghost"})
        assert response.status_code == 404

    def test_get_not_allowed(self, client, maya):
        client.force_login(maya)
        assert client.get(reverse("chat:start_direct")).status_code == 405


@pytest.mark.django_db
class TestStartGroup:
    def test_creates_group_with_creator(self, client, maya, arjun):
        User.objects.create_user("ops", password="pw")
        client.force_login(maya)
        response = client.post(
            reverse("chat:start_group"),
            {"name": " Design team ", "members": ["arjun", "@ops", "maya"]},
        )
        room = Room.objects.get(type=Room.RoomTypes.GROUP)
        assert room.name == "Design team"
        assert set(room.members.values_list("username", flat=True)) == {
            "maya",
            "arjun",
            "ops",
        }
        assert response.url == f"/chat/?room={room.id}"

    @pytest.mark.parametrize(
        "data, error",
        [
            ({"name": "", "members": ["arjun"]}, "Give the group a name."),
            ({"name": "x" * 51, "members": ["arjun"]}, "at most 50 characters"),
            ({"name": "Solo", "members": []}, "Add at least one other person."),
            ({"name": "Solo", "members": ["maya"]}, "Add at least one other person."),
            ({"name": "Team", "members": ["ghost"]}, "Unknown people: ghost."),
        ],
    )
    def test_rejects_bad_input(self, client, maya, arjun, data, error):
        client.force_login(maya)
        response = client.post(reverse("chat:start_group"), data, follow=True)
        assert Room.objects.count() == 0
        assert error in response.content.decode()

    def test_new_chat_dialog_on_page(self, client, maya):
        client.force_login(maya)
        html = client.get(reverse("chat:chat")).content.decode()
        assert 'id="new-chat"' in html
        assert reverse("chat:start_group") in html


@pytest.mark.django_db
class TestHistoryEndpoint:
    def url(self, room):
        return reverse("chat:history", args=[room.id])

    def test_pages_backwards_without_gaps(self, client, maya, room):
        make_messages(room, maya, 120)
        client.force_login(maya)
        first = client.get(self.url(room)).json()
        assert [m["message"] for m in first["messages"]][-1] == "m119"
        assert first["has_more"] is True
        seen = [m["message"] for m in first["messages"]]
        before = first["messages"][0]["id"]
        while True:
            page = client.get(self.url(room), {"before": before}).json()
            seen = [m["message"] for m in page["messages"]] + seen
            if not page["has_more"]:
                break
            before = page["messages"][0]["id"]
        assert seen == [f"m{i}" for i in range(120)]

    def test_limit_is_clamped(self, client, maya, room):
        make_messages(room, maya, 5)
        client.force_login(maya)
        assert len(client.get(self.url(room), {"limit": 2}).json()["messages"]) == 2
        assert len(client.get(self.url(room), {"limit": 0}).json()["messages"]) == 1
        assert len(client.get(self.url(room), {"limit": "x"}).json()["messages"]) == 5

    def test_non_member_gets_404(self, client, room):
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        assert client.get(self.url(room)).status_code == 404

    def test_unknown_before_is_400(self, client, maya, room):
        client.force_login(maya)
        response = client.get(self.url(room), {"before": "not-a-uuid"})
        assert response.status_code == 400

    def test_hides_cleared_messages(self, client, maya, arjun, room):
        hidden = make_messages(room, arjun, 1)[0]
        hidden.visible_for.remove(maya)
        client.force_login(maya)
        assert client.get(self.url(room)).json()["messages"] == []


@pytest.mark.django_db(transaction=True)
class TestEditDelete:
    async def connect_pair(self, maya, arjun, room):
        sender = make_communicator(room.id, maya)
        other = make_communicator(room.id, arjun)
        await sender.connect()
        await other.connect()
        await sender.send_json_to({"type": "save_message", "message": "first"})
        saved = await sender.receive_json_from()
        await other.receive_json_from()
        return sender, other, saved["id"]

    async def test_edit_own_message(self, maya, arjun, room):
        sender, other, message_id = await self.connect_pair(maya, arjun, room)
        await sender.send_json_to(
            {"type": "edit_message", "id": message_id, "message": " second "}
        )
        update = await other.receive_json_from()
        assert update["type"] == "message_updated"
        assert (update["message"], update["edited"], update["deleted"]) == (
            "second",
            True,
            False,
        )
        stored = await database_sync_to_async(Message.objects.get)(id=message_id)
        assert stored.content == "second" and stored.edited_at is not None
        await sender.disconnect()
        await other.disconnect()

    async def test_delete_own_message_clears_content(self, maya, arjun, room):
        sender, other, message_id = await self.connect_pair(maya, arjun, room)
        await sender.send_json_to({"type": "delete_message", "id": message_id})
        update = await other.receive_json_from()
        assert (update["deleted"], update["message"]) == (True, "")
        stored = await database_sync_to_async(Message.objects.get)(id=message_id)
        assert stored.content == "" and stored.deleted_at is not None
        await sender.disconnect()
        await other.disconnect()

    async def test_cannot_change_someone_elses_message(self, maya, arjun, room):
        sender, other, message_id = await self.connect_pair(maya, arjun, room)
        for payload in (
            {"type": "edit_message", "id": message_id, "message": "hacked"},
            {"type": "delete_message", "id": message_id},
        ):
            await other.send_json_to(payload)
            error = await other.receive_json_from()
            assert (error["type"], error["code"]) == ("error", 403)
        assert await sender.receive_nothing()
        stored = await database_sync_to_async(Message.objects.get)(id=message_id)
        assert stored.content == "first"
        await sender.disconnect()
        await other.disconnect()

    async def test_cannot_edit_deleted_or_empty(self, maya, arjun, room):
        sender, other, message_id = await self.connect_pair(maya, arjun, room)
        await sender.send_json_to(
            {"type": "edit_message", "id": message_id, "message": "  "}
        )
        assert (await sender.receive_json_from())["type"] == "error"
        await sender.send_json_to({"type": "delete_message", "id": message_id})
        await sender.receive_json_from()
        await other.receive_json_from()
        await sender.send_json_to(
            {"type": "edit_message", "id": message_id, "message": "back"}
        )
        assert (await sender.receive_json_from())["code"] == 403
        await sender.disconnect()
        await other.disconnect()

    async def test_bad_id_is_rejected(self, maya, room):
        sender = make_communicator(room.id, maya)
        await sender.connect()
        await sender.send_json_to({"type": "delete_message", "id": "nope"})
        assert (await sender.receive_json_from())["code"] == 403
        await sender.disconnect()


@pytest.mark.django_db
class TestDeletedInViews:
    def test_deleted_message_hidden_from_preview_and_payload(self, client, maya, room):
        from django.utils import timezone

        m = make_messages(room, maya, 1)[0]
        Message.objects.filter(pk=m.pk).update(deleted_at=timezone.now(), content="")
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.context["rooms"][0]["last_content"] == ""
        assert response.context["room_messages"][0]["deleted"] is True


@pytest.mark.django_db
class TestUnreadCounts:
    def test_counts_messages_from_others_after_last_read(self, maya, arjun, room):
        from datetime import timedelta

        from chat.presence import mark_read, unread_count

        msgs = make_messages(room, arjun, 3)
        make_messages(room, maya, 1)  # own messages never count
        assert unread_count(maya, room) == 3
        mark_read(maya, room, msgs[0].created_at + timedelta(milliseconds=1))
        assert unread_count(maya, room) == 2

    def test_skips_deleted_and_cleared(self, maya, arjun, room):
        from django.utils import timezone

        from chat.presence import unread_count

        deleted, cleared, kept = make_messages(room, arjun, 3)
        Message.objects.filter(pk=deleted.pk).update(deleted_at=timezone.now())
        cleared.visible_for.remove(maya)
        assert unread_count(maya, room) == 1

    def test_opening_room_marks_it_read(self, client, maya, arjun, room):
        make_messages(room, arjun, 2)
        client.force_login(maya)
        listed = client.get(reverse("chat:chat")).context["rooms"]
        assert listed[0]["unread"] == 2
        opened = client.get(reverse("chat:chat"), {"room": room.id}).context
        assert opened["room_summary"]["unread"] == 0
        assert client.get(reverse("chat:chat")).context["rooms"][0]["unread"] == 0

    def test_room_summary_has_presence_fields(self, client, maya, arjun, room):
        client.force_login(maya)
        summary = client.get(reverse("chat:chat")).context["rooms"][0]
        assert summary["other_username"] == "arjun"
        assert sorted(summary["member_usernames"]) == ["arjun", "maya"]


@pytest.mark.django_db
class TestPresenceHelpers:
    def test_online_window(self, maya):
        from datetime import timedelta

        from django.utils import timezone

        from chat.models import Connection
        from chat.presence import ONLINE_WINDOW, is_online, open_connection

        assert open_connection(maya, "c1") is True
        assert open_connection(maya, "c2") is False  # already online
        assert is_online(maya)
        Connection.objects.update(
            last_seen=timezone.now() - ONLINE_WINDOW - timedelta(1)
        )
        assert not is_online(maya)

    def test_close_reports_last_connection(self, maya):
        from chat.presence import close_connection, open_connection

        open_connection(maya, "c1")
        open_connection(maya, "c2")
        assert close_connection(maya, "c1") is False
        assert close_connection(maya, "c2") is True


def make_inbox(user):
    communicator = WebsocketCommunicator(
        application, "/inbox/", headers=[(b"origin", b"http://localhost")]
    )
    communicator.scope["user"] = user
    return communicator


@pytest.mark.django_db(transaction=True)
class TestLiveFeatures:
    async def test_typing_reaches_others_and_is_throttled(self, maya, arjun, room):
        sender = make_communicator(room.id, maya)
        other = make_communicator(room.id, arjun)
        await sender.connect()
        await other.connect()
        await sender.send_json_to({"type": "typing"})
        await sender.send_json_to({"type": "typing"})  # within a second: dropped
        event = await other.receive_json_from()
        assert (event["type"], event["user"]) == ("typing", "maya")
        assert await other.receive_nothing(timeout=0.3)
        await sender.disconnect()
        await other.disconnect()

    async def test_read_frame_updates_read_state(self, maya, arjun, room):
        from chat.models import ReadState

        make = database_sync_to_async(make_messages)
        await make(room, arjun, 2)
        communicator = make_communicator(room.id, maya)
        await communicator.connect()
        await communicator.send_json_to({"type": "read"})
        await communicator.receive_nothing(timeout=0.2)
        count = await database_sync_to_async(
            ReadState.objects.filter(user=maya, room=room).count
        )()
        assert count == 1
        await communicator.disconnect()

    async def test_inbox_requires_login(self):
        from django.contrib.auth.models import AnonymousUser

        connected, code = await make_inbox(AnonymousUser()).connect()
        assert (connected, code) == (False, 4401)

    async def test_presence_snapshot_and_updates(self, maya, arjun, room):
        arjun_inbox = make_inbox(arjun)
        await arjun_inbox.connect()
        assert (await arjun_inbox.receive_json_from()) == {
            "type": "presence_snapshot",
            "online": [],
        }

        maya_inbox = make_inbox(maya)
        await maya_inbox.connect()
        assert (await maya_inbox.receive_json_from())["online"] == ["arjun"]
        assert (await arjun_inbox.receive_json_from()) == {
            "type": "presence",
            "user": "maya",
            "online": True,
        }

        await maya_inbox.send_json_to({"type": "ping"})
        assert (await maya_inbox.receive_json_from())["type"] == "presence_snapshot"

        await maya_inbox.disconnect()
        assert (await arjun_inbox.receive_json_from()) == {
            "type": "presence",
            "user": "maya",
            "online": False,
        }
        await arjun_inbox.disconnect()

    async def test_presence_not_sent_to_strangers(self, maya, room):
        stranger = await database_sync_to_async(User.objects.create_user)(
            "eve", password="pw"
        )
        eve_inbox = make_inbox(stranger)
        await eve_inbox.connect()
        await eve_inbox.receive_json_from()
        maya_inbox = make_inbox(maya)
        await maya_inbox.connect()
        await maya_inbox.receive_json_from()
        assert await eve_inbox.receive_nothing(timeout=0.3)
        await maya_inbox.disconnect()
        await eve_inbox.disconnect()

    async def test_new_message_reaches_inboxes_with_unread(self, maya, arjun, room):
        arjun_inbox = make_inbox(arjun)
        await arjun_inbox.connect()
        await arjun_inbox.receive_json_from()  # snapshot

        sender = make_communicator(room.id, maya)
        await sender.connect()
        await sender.send_json_to({"type": "save_message", "message": "ping"})
        await sender.receive_json_from()

        activity = await arjun_inbox.receive_json_from()
        assert activity["type"] == "room_activity"
        assert activity["room"] == str(room.id)
        assert activity["unread"] == 1
        assert activity["message"]["message"] == "ping"
        await sender.disconnect()
        await arjun_inbox.disconnect()

    async def test_sending_marks_sender_read(self, maya, arjun, room):
        from chat.presence import unread_count

        await database_sync_to_async(make_messages)(room, arjun, 2)
        sender = make_communicator(room.id, maya)
        await sender.connect()
        await sender.send_json_to({"type": "save_message", "message": "reply"})
        await sender.receive_json_from()
        assert await database_sync_to_async(unread_count)(maya, room) == 0
        await sender.disconnect()
