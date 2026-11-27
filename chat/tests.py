import json

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


def assert_unavailable_redirect(client, room_param):
    """`/chat/?room=...` sends you to `/chat/` with the same notice whatever
    the reason (no existence leak)."""
    from django.contrib.messages import INFO, get_messages

    from chat.views import ROOM_UNAVAILABLE

    response = client.get(reverse("chat:chat"), {"room": room_param})
    assert response.status_code == 302
    assert response.url == reverse("chat:chat")
    notices = [(m.level, m.message) for m in get_messages(response.wsgi_request)]
    assert notices == [(INFO, ROOM_UNAVAILABLE)]
    return response


@pytest.mark.django_db
class TestChatViewAccess:
    def test_non_member_is_redirected_with_notice(self, client, room):
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        assert_unavailable_redirect(client, room.id)

    def test_malformed_room_id_is_redirected(self, client, maya):
        client.force_login(maya)
        assert_unavailable_redirect(client, "not-a-uuid")

    def test_unknown_room_is_redirected(self, client, maya):
        import uuid

        client.force_login(maya)
        assert_unavailable_redirect(client, uuid.uuid4())

    def test_removed_member_sees_notice_on_chats(self, client, group, maya, lee):
        from chat import groups
        from chat.views import ROOM_UNAVAILABLE

        groups.remove_member(group, maya, lee)
        client.force_login(lee)
        response = client.get(reverse("chat:chat"), {"room": group.id}, follow=True)
        assert response.redirect_chain == [(reverse("chat:chat"), 302)]
        assert response.context["room"] is None
        assert ROOM_UNAVAILABLE.replace("'", "&#x27;") in response.content.decode()

    def test_deleted_room_is_redirected(self, client, group, maya):
        from chat import groups

        group_id = group.id
        groups.delete_group(group, maya)
        client.force_login(maya)
        assert_unavailable_redirect(client, group_id)

    def test_other_endpoints_keep_404(self, client, room):
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        for name in ("history", "details", "summary"):
            url = reverse(f"chat:{name}", args=[room.id])
            assert client.get(url).status_code == 404

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
        [
            ("Maya Rao", "MR"),
            ("maya", "MA"),
            ("@ops", "OP"),
            ("@lee", "LE"),
            ("", "?"),
            ("a", "A"),
            ("<img src=x onerror=alert(2)>", "IS"),
            ("!!!", "?"),
            ("!!! ???", "?"),
            ("--- Lee", "LE"),
            ("(Design) team", "DT"),
            ("Q3 2026", "Q2"),
            ("Émile Zola", "ÉZ"),
            ("   ", "?"),
            (None, "?"),
        ],
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


@pytest.mark.django_db
class TestQueryBudget:
    def test_chat_page_queries_do_not_grow_with_rooms(self, client, maya, arjun):
        """docs/architecture.md promises a fixed number of queries per page."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(maya)
        counts = []
        for total in (2, 10):
            for i in range(total - Room.objects.count()):
                r = Room.objects.create(name=f"r{i}", type=Room.RoomTypes.GROUP)
                r.members.add(maya, arjun)
                make_messages(r, arjun, 1)
            with CaptureQueriesContext(connection) as ctx:
                client.get(reverse("chat:chat"))
            counts.append(len(ctx.captured_queries))
        assert counts[0] == counts[1]


# Group admins (P9a)


@pytest.fixture
def lee(db):
    return User.objects.create_user("lee", password="pw", first_name="Lee")


@pytest.fixture
def group(maya, arjun, lee):
    """Design team: maya created it (admin); arjun and lee are members."""
    from chat.services import create_group_room

    return create_group_room(maya, "Design team", ["arjun", "lee"])


def member(room, user):
    from chat.models import Membership

    return Membership.objects.get(room=room, user=user)


def system_texts(room):
    return list(
        Message.objects.filter(room=room, kind=Message.Kinds.SYSTEM)
        .order_by("created_at")
        .values_list("content", flat=True)
    )


@pytest.mark.django_db
class TestGroupRules:
    def test_creator_is_admin_and_creator(self, group, maya, arjun):
        assert group.created_by == maya
        assert member(group, maya).is_admin
        assert not member(group, arjun).is_admin

    def test_any_member_can_add(self, group, arjun):
        from chat import groups

        User.objects.create_user("sofia", password="pw", first_name="Sofia")
        groups.add_members(group, arjun, ["sofia"])
        assert group.members.filter(username="sofia").exists()
        assert system_texts(group)[-1] == "arjun added Sofia"

    def test_add_rejects_existing_unknown_and_too_many(self, group, maya):
        from chat import groups

        with pytest.raises(groups.GroupError, match="nobody_new"):
            groups.add_members(group, maya, ["arjun"])
        with pytest.raises(groups.GroupError, match="unknown_people"):
            groups.add_members(group, maya, ["ghost"])
        for i in range(47):
            User.objects.create_user(f"user{i}", password="pw")
        with pytest.raises(groups.GroupError, match="too_many"):
            groups.add_members(group, maya, [f"user{i}" for i in range(48)])

    def test_only_admins_rename_remove_and_delete(self, group, arjun, lee):
        from chat import groups

        for action in (
            lambda: groups.rename(group, arjun, "Mine now"),
            lambda: groups.remove_member(group, arjun, lee),
            lambda: groups.delete_group(group, arjun),
            lambda: groups.set_admin(group, arjun, lee, True),
        ):
            with pytest.raises(groups.GroupError, match="not_admin"):
                action()
        group.refresh_from_db()
        assert group.name == "Design team"

    def test_admin_actions_and_system_messages(self, group, maya, arjun, lee):
        from chat import groups

        groups.rename(group, maya, "Design crew")
        groups.set_admin(group, maya, arjun, True)
        groups.remove_member(group, maya, lee)
        group.refresh_from_db()
        assert group.name == "Design crew"
        assert member(group, arjun).is_admin
        assert not group.members.filter(pk=lee.pk).exists()
        assert system_texts(group) == [
            'maya renamed the group to "Design crew"',
            "maya made arjun an admin",
            "maya removed Lee",
        ]

    def test_only_admin_cannot_step_down_until_another_admin(self, group, maya, arjun):
        from chat import groups

        with pytest.raises(groups.GroupError, match="last_admin"):
            groups.set_admin(group, maya, maya, False)
        groups.set_admin(group, maya, arjun, True)
        groups.set_admin(group, maya, maya, False)
        assert not member(group, maya).is_admin
        assert system_texts(group)[-1] == "maya is no longer an admin"

    def test_admin_can_demote_another_admin(self, group, maya, arjun):
        from chat import groups

        groups.set_admin(group, maya, arjun, True)
        groups.set_admin(group, maya, arjun, False)
        assert not member(group, arjun).is_admin
        assert system_texts(group)[-1] == "maya removed arjun as admin"

    def test_admin_cannot_remove_self(self, group, maya):
        from chat import groups

        with pytest.raises(groups.GroupError, match="remove_self"):
            groups.remove_member(group, maya, maya)

    def test_last_admin_leaving_promotes_longest_standing(self, group, maya, arjun):
        from datetime import timedelta

        from django.utils import timezone

        from chat import groups

        # lee joined before arjun
        member_lee = group.memberships.get(user__username="lee")
        member_lee.joined_at = timezone.now() - timedelta(days=1)
        member_lee.save()
        assert groups.leave(group, maya) is True
        assert member(group, member_lee.user).is_admin
        assert not member(group, arjun).is_admin
        assert system_texts(group)[-2:] == ["maya left", "Lee is now an admin"]

    def test_leaving_with_other_admins_promotes_no_one(self, group, maya, arjun):
        from chat import groups

        groups.set_admin(group, maya, arjun, True)
        groups.leave(group, maya)
        admins = list(
            group.memberships.filter(is_admin=True).values_list(
                "user__username", flat=True
            )
        )
        assert admins == ["arjun"]

    def test_last_member_leaving_deletes_group(self, group, maya, arjun, lee):
        from chat import groups

        groups.leave(group, arjun)
        groups.leave(group, lee)
        assert groups.leave(group, maya) is False
        assert not Room.objects.filter(pk=group.pk).exists()

    def test_private_rooms_are_not_managed(self, room, maya, arjun):
        from chat import groups

        with pytest.raises(groups.GroupError, match="not_group"):
            groups.leave(room, maya)

    def test_system_messages_are_not_unread_or_previews(
        self, group, maya, arjun, client
    ):
        from chat import groups
        from chat.presence import unread_count

        groups.rename(group, maya, "Renamed")
        assert unread_count(arjun, group) == 0
        client.force_login(arjun)
        summary = client.get(reverse("chat:chat")).context["rooms"][0]
        assert summary["last_content"] == ""


class TestGroupErrorMessages:
    def test_every_raised_code_has_a_message(self):
        import re
        from pathlib import Path

        from chat import groups

        source = Path(groups.__file__).read_text()
        raised = set(re.findall(r'raise GroupError\("([a-z_]+)"\)', source))
        assert raised and raised <= set(groups.GROUP_ERROR_MESSAGES)

    def test_unknown_code_has_a_safe_fallback(self):
        from chat import groups

        assert groups.error_message("nope") == groups.UNKNOWN_ERROR_MESSAGE


@pytest.mark.django_db
class TestGroupEndpoints:
    def post(self, client, room, action, data=None, json=True):
        headers = {"HTTP_ACCEPT": "application/json"} if json else {}
        return client.post(
            reverse("chat:group_action", args=[room.id, action]), data or {}, **headers
        )

    def test_details_panel_for_admin_and_member(self, client, group, maya, arjun):
        client.force_login(maya)
        html = client.get(reverse("chat:details", args=[group.id])).content.decode()
        assert (
            "Rename group" in html and "Delete group" in html and "Make admin" in html
        )
        assert "Created by maya" in html
        client.force_login(arjun)
        html = client.get(reverse("chat:details", args=[group.id])).content.decode()
        assert "Rename group" not in html and "Delete group" not in html
        assert "Make admin" not in html
        assert "+ Add people" in html and "Leave group" in html

    def test_only_admin_sees_step_down_note(self, client, group, maya):
        client.force_login(maya)
        html = client.get(reverse("chat:details", args=[group.id])).content.decode()
        assert "only admin" in html

    def test_details_for_direct_chat(self, client, room, maya):
        client.force_login(maya)
        html = client.get(reverse("chat:details", args=[room.id])).content.decode()
        assert "@arjun" in html and "Clear history" in html
        assert "Leave group" not in html

    def test_details_hidden_from_non_members(self, client, group):
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        assert client.get(reverse("chat:details", args=[group.id])).status_code == 404
        assert self.post(client, group, "leave").status_code == 404

    def test_rename_and_errors_as_json(self, client, group, maya, arjun):
        client.force_login(maya)
        assert self.post(client, group, "rename", {"name": "New"}).json() == {
            "ok": True,
            "redirect": None,
        }
        client.force_login(arjun)
        response = self.post(client, group, "rename", {"name": "Nope"})
        assert response.status_code == 400
        assert response.json()["error"] == "Only admins can do that."

    def test_make_admin_remove_and_add(self, client, group, maya, arjun, lee):
        client.force_login(maya)
        self.post(client, group, "make-admin", {"username": "arjun"})
        self.post(client, group, "remove", {"username": "lee"})
        User.objects.create_user("sofia", password="pw")
        self.post(client, group, "add", {"members": ["sofia"]})
        assert member(group, arjun).is_admin
        assert set(group.members.values_list("username", flat=True)) == {
            "maya",
            "arjun",
            "sofia",
        }

    def test_leave_and_delete_redirect_to_list(self, client, group, maya, arjun):
        client.force_login(arjun)
        assert self.post(client, group, "leave").json()["redirect"] == "/chat/"
        client.force_login(maya)
        assert self.post(client, group, "delete").json()["redirect"] == "/chat/"
        assert not Room.objects.filter(pk=group.pk).exists()

    def test_form_fallback_redirects_with_notice(self, client, group, arjun):
        client.force_login(arjun)
        response = self.post(client, group, "rename", {"name": "x"}, json=False)
        assert response.url == f"/chat/?room={group.id}"
        response = client.get(response.url)
        assert "Only admins can do that." in response.content.decode()

    def test_json_errors_come_from_the_message_table(self, client, group, maya):
        from chat import groups

        client.force_login(maya)
        response = self.post(client, group, "add", {"members": ["ghost"]})
        assert response.json()["error"] == groups.GROUP_ERROR_MESSAGES["unknown_people"]
        assert "ghost" not in response.content.decode()

    def test_unknown_action_and_get(self, client, group, maya):
        client.force_login(maya)
        assert self.post(client, group, "explode").status_code == 404
        url = reverse("chat:group_action", args=[group.id, "leave"])
        assert client.get(url).status_code == 405


@pytest.mark.django_db(transaction=True)
class TestGroupSockets:
    async def test_removed_member_is_disconnected(self, maya, arjun, lee):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(
            maya, "Team", ["arjun", "lee"]
        )
        lee_socket = make_communicator(group.id, lee)
        maya_socket = make_communicator(group.id, maya)
        await lee_socket.connect()
        await maya_socket.connect()

        await database_sync_to_async(groups.remove_member)(group, maya, lee)

        seen_by_maya = [await maya_socket.receive_json_from() for _ in range(2)]
        assert [f["type"] for f in seen_by_maya] == ["save_message", "room_updated"]
        assert seen_by_maya[0]["kind"] == "system"
        assert seen_by_maya[1]["member_count"] == 2

        frames = []
        while True:
            output = await lee_socket.receive_output()
            if output["type"] == "websocket.close":
                break
            frames.append(json.loads(output["text"]))
        assert output["code"] == 4403
        assert frames[-1]["code"] == 403
        await lee_socket.disconnect()
        await maya_socket.disconnect()

    async def test_frames_from_ex_member_are_refused(self, maya, arjun, lee):
        from chat.models import Membership
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(maya, "Team", ["lee"])
        lee_socket = make_communicator(group.id, lee)
        await lee_socket.connect()
        # Removed without an event (e.g. by another process that crashed)
        await database_sync_to_async(
            Membership.objects.filter(room=group, user=lee).delete
        )()
        await lee_socket.send_json_to({"type": "save_message", "message": "hi"})
        assert (await lee_socket.receive_json_from())["code"] == 403
        assert (await lee_socket.receive_output())["code"] == 4403
        await lee_socket.disconnect()
        count = await database_sync_to_async(Message.objects.filter(room=group).count)()
        assert count == 0

    async def test_deleting_group_closes_sockets(self, maya, arjun):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(maya, "Team", ["arjun"])
        socket = make_communicator(group.id, arjun)
        await socket.connect()
        await database_sync_to_async(groups.delete_group)(group, maya)
        assert (await socket.receive_json_from())["code"] == 404
        assert (await socket.receive_output())["code"] == 4404
        await socket.disconnect()

    async def test_system_messages_cannot_be_edited(self, maya, arjun):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(maya, "Team", ["arjun"])
        await database_sync_to_async(groups.rename)(group, maya, "Renamed")
        system = await database_sync_to_async(
            Message.objects.filter(room=group, kind="system").first
        )()
        socket = make_communicator(group.id, maya)
        await socket.connect()
        await socket.send_json_to({"type": "delete_message", "id": str(system.id)})
        assert (await socket.receive_json_from())["code"] == 403
        await socket.disconnect()


@pytest.mark.django_db
class TestGroupAdminMigration:
    def test_backfill_makes_earliest_member_admin(self, maya, arjun, lee):
        import importlib

        from django.apps import apps

        from chat.models import Membership

        g = Room.objects.create(name="Old group", type=Room.RoomTypes.GROUP)
        for u in (arjun, maya, lee):  # arjun added first
            Membership.objects.create(room=g, user=u)
        dm = Room.objects.create(name="dm", type=Room.RoomTypes.PRIVATE)
        dm.members.add(maya, arjun)

        module = importlib.import_module("chat.migrations.0004_group_admins")
        module.backfill(apps, None)

        g.refresh_from_db()
        assert g.created_by == arjun
        assert list(
            g.memberships.filter(is_admin=True).values_list("user__username", flat=True)
        ) == ["arjun"]
        assert not dm.memberships.filter(is_admin=True).exists()
        assert set(g.memberships.values_list("joined_at", flat=True)) == {g.created_at}


# Live room list (P9b)


@pytest.mark.django_db
class TestRoomSummary:
    def test_summary_is_per_viewer(self, maya, arjun, room):
        from chat.presenters import room_summary

        assert room_summary(maya, room.id)["title"] == "arjun"
        assert room_summary(arjun, room.id)["title"] == "maya"
        outsider = User.objects.create_user("eve", password="pw")
        assert room_summary(outsider, room.id) is None

    def test_summary_endpoint(self, client, maya, room):
        client.force_login(maya)
        data = client.get(reverse("chat:summary", args=[room.id])).json()
        assert data["id"] == str(room.id) and data["other_username"] == "arjun"
        outsider = User.objects.create_user("eve", password="pw")
        client.force_login(outsider)
        assert client.get(reverse("chat:summary", args=[room.id])).status_code == 404


async def next_frame_of_type(communicator, frame_type, attempts=5):
    for _ in range(attempts):
        frame = await communicator.receive_json_from(timeout=2)
        if frame["type"] == frame_type:
            return frame
    raise AssertionError(f"no {frame_type} frame")


@pytest.mark.django_db(transaction=True)
class TestLiveRoomList:
    async def open_inbox(self, user):
        inbox = make_inbox(user)
        await inbox.connect()
        await inbox.receive_json_from()  # presence snapshot
        return inbox

    async def test_new_group_reaches_members(self, maya, arjun, lee):
        from chat.services import create_group_room

        arjun_inbox = await self.open_inbox(arjun)
        group = await database_sync_to_async(create_group_room)(maya, "Team", ["arjun"])
        frame = await next_frame_of_type(arjun_inbox, "room_added")
        assert frame["room"]["id"] == str(group.id)
        assert frame["room"]["title"] == "Team"
        assert frame["room"]["type"] == "group"
        await arjun_inbox.disconnect()

    async def test_new_direct_chat_reaches_both_with_their_own_title(self, maya, arjun):
        from chat.services import get_or_create_direct_room

        maya_inbox = await self.open_inbox(maya)
        arjun_inbox = await self.open_inbox(arjun)
        room, created = await database_sync_to_async(get_or_create_direct_room)(
            maya, arjun
        )
        assert created
        assert (await next_frame_of_type(arjun_inbox, "room_added"))["room"][
            "title"
        ] == "maya"
        assert (await next_frame_of_type(maya_inbox, "room_added"))["room"][
            "title"
        ] == "arjun"
        # Reusing it sends nothing.
        await database_sync_to_async(get_or_create_direct_room)(maya, arjun)
        assert await arjun_inbox.receive_nothing(timeout=0.3)
        await maya_inbox.disconnect()
        await arjun_inbox.disconnect()

    async def test_added_renamed_removed(self, maya, arjun, lee):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(maya, "Team", ["arjun"])
        lee_inbox = await self.open_inbox(lee)
        arjun_inbox = await self.open_inbox(arjun)

        await database_sync_to_async(groups.add_members)(group, arjun, ["lee"])
        assert (await next_frame_of_type(lee_inbox, "room_added"))["room"][
            "title"
        ] == "Team"

        await database_sync_to_async(groups.rename)(group, maya, "Crew")
        changed = await next_frame_of_type(arjun_inbox, "room_changed")
        assert (changed["room"]["title"], changed["room"]["initials"]) == ("Crew", "CR")

        await database_sync_to_async(groups.remove_member)(group, maya, lee)
        removed = await next_frame_of_type(lee_inbox, "room_removed")
        assert removed["room"] == str(group.id)
        await lee_inbox.disconnect()
        await arjun_inbox.disconnect()

    async def test_leave_and_delete(self, maya, arjun, lee):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(
            maya, "Team", ["arjun", "lee"]
        )
        group_id = str(group.id)  # delete() clears the instance's pk
        arjun_inbox = await self.open_inbox(arjun)
        lee_inbox = await self.open_inbox(lee)

        await database_sync_to_async(groups.leave)(group, arjun)
        left = await next_frame_of_type(arjun_inbox, "room_removed")
        assert left["room"] == group_id

        await database_sync_to_async(groups.delete_group)(group, maya)
        deleted = await next_frame_of_type(lee_inbox, "room_removed")
        assert deleted["room"] == group_id
        await arjun_inbox.disconnect()
        await lee_inbox.disconnect()


# Live-room fixes (P9c)


def make_users(prefix, count):
    return [
        User.objects.create_user(f"{prefix}{i}", password="pw", first_name=f"P{i}")
        for i in range(count)
    ]


def count_queries(func, on_commit):
    """Queries run by `func()` plus the on_commit callbacks it queues."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        with on_commit(execute=True):
            func()
    return len(ctx.captured_queries)


@pytest.fixture
def inbox_sends():
    """Every send_to_inbox call as (user pk, event), without a channel layer."""
    from unittest import mock

    calls = []
    with mock.patch(
        "chat.live_rooms.realtime.send_to_inbox",
        side_effect=lambda pk, event: calls.append((pk, event)),
    ):
        yield calls


@pytest.mark.django_db
class TestRoomSummariesForUsers:
    def test_matches_room_summary_for_each_viewer(self, maya, arjun, lee, group):
        from chat import presence
        from chat.presenters import room_summaries_for_users, room_summary

        make_messages(group, arjun, 3)
        latest = Message.objects.filter(room=group).order_by("-created_at").first()
        presence.mark_read(lee, group, latest.created_at)
        hidden = Message.objects.create(content="later", room=group, user=lee)
        hidden.visible_for.add(lee, arjun)  # maya cleared it
        outsider = User.objects.create_user("eve", password="pw")

        result = room_summaries_for_users(group.id, [maya, arjun, lee, outsider])
        assert set(result) == {maya.pk, arjun.pk, lee.pk}
        for user in (maya, arjun, lee):
            assert result[user.pk] == room_summary(user, group.id)
        assert result[maya.pk]["unread"] == 3
        assert result[maya.pk]["last_content"] == "m2"
        assert result[lee.pk]["last_is_mine"] is True
        assert result[lee.pk]["unread"] == 0
        assert result[arjun.pk]["unread"] == 1

    def test_direct_room_titles_are_per_viewer(self, maya, arjun, room):
        from chat.presenters import room_summaries_for_users

        result = room_summaries_for_users(room.id, [maya, arjun])
        assert (result[maya.pk]["title"], result[arjun.pk]["title"]) == (
            "arjun",
            "maya",
        )

    def test_missing_room(self, maya):
        import uuid

        from chat.presenters import room_summaries_for_users

        assert room_summaries_for_users(uuid.uuid4(), [maya]) == {}


@pytest.mark.django_db
class TestLiveRoomQueries:
    """Building live-room frames doesn't grow with the number of people."""

    def test_create_group_room(
        self, maya, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat.services import MAX_GROUP_MEMBERS, create_group_room

        people = make_users("p", MAX_GROUP_MEMBERS - 1)
        counts = [
            count_queries(
                lambda n=n: create_group_room(
                    maya, f"G{n}", [u.username for u in people[:n]]
                ),
                django_capture_on_commit_callbacks,
            )
            for n in (1, MAX_GROUP_MEMBERS - 1)  # 2 and 50 members
        ]
        assert counts[0] == counts[1]
        assert len(inbox_sends) == 2 + MAX_GROUP_MEMBERS

    def test_add_members(self, maya, inbox_sends, django_capture_on_commit_callbacks):
        from chat import groups
        from chat.services import create_group_room

        people = make_users("p", 41)
        counts = []
        for n in (1, 40):
            g = create_group_room(maya, f"G{n}", [people[-1].username])
            counts.append(
                count_queries(
                    lambda: groups.add_members(
                        g, maya, [u.username for u in people[:n]]
                    ),
                    django_capture_on_commit_callbacks,
                )
            )
        assert counts[0] == counts[1]
        assert len(inbox_sends) == 41

    def test_rename(self, maya, inbox_sends, django_capture_on_commit_callbacks):
        from chat import groups
        from chat.services import MAX_GROUP_MEMBERS, create_group_room

        people = make_users("p", MAX_GROUP_MEMBERS - 1)
        counts = []
        for n in (2, MAX_GROUP_MEMBERS - 1):  # 3 and 50 members
            g = create_group_room(maya, f"G{n}", [u.username for u in people[:n]])
            counts.append(
                count_queries(
                    lambda: groups.rename(g, maya, "Renamed"),
                    django_capture_on_commit_callbacks,
                )
            )
        assert counts[0] == counts[1]
        assert len(inbox_sends) == 3 + MAX_GROUP_MEMBERS

    def test_room_added_objects_match_room_summary(
        self, maya, arjun, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat.presenters import room_summary
        from chat.services import create_group_room

        with django_capture_on_commit_callbacks(execute=True):
            g = create_group_room(maya, "Team", ["arjun", "lee"])
        assert sorted(pk for pk, _ in inbox_sends) == sorted(
            [maya.pk, arjun.pk, lee.pk]
        )
        for pk, event in inbox_sends:
            assert event["frame"] == "room_added"
            assert event["room"] == room_summary(User.objects.get(pk=pk), g.id)


@pytest.mark.django_db
class TestRoomChangedFrame:
    def test_one_partial_frame_for_every_member(
        self, group, maya, arjun, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups

        with django_capture_on_commit_callbacks(execute=True):
            groups.rename(group, maya, "Crew")
        assert sorted(pk for pk, _ in inbox_sends) == sorted(
            [maya.pk, arjun.pk, lee.pk]
        )
        events = [event for _, event in inbox_sends]
        assert all(event == events[0] for event in events)
        assert events[0]["frame"] == "room_changed"
        room = events[0]["room"]
        assert set(room) == {
            "id",
            "title",
            "initials",
            "member_count",
            "member_usernames",
        }
        assert (room["id"], room["title"], room["initials"]) == (
            str(group.id),
            "Crew",
            "CR",
        )
        assert room["member_count"] == 3
        assert sorted(room["member_usernames"]) == ["arjun", "lee", "maya"]

    def test_not_sent_for_direct_rooms(
        self, room, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import live_rooms

        with django_capture_on_commit_callbacks(execute=True):
            live_rooms.room_changed(room)
        assert inbox_sends == []


@pytest.mark.django_db
class TestLiveRoomFailures:
    def test_failed_send_is_logged_and_skipped(
        self, maya, arjun, lee, caplog, django_capture_on_commit_callbacks
    ):
        import logging
        from unittest import mock

        from chat.services import create_group_room

        delivered = []

        def send(pk, event):
            if pk == arjun.pk:
                raise RuntimeError("channel layer is down for arjun")
            delivered.append(pk)

        with mock.patch("chat.live_rooms.realtime.send_to_inbox", side_effect=send):
            with caplog.at_level(logging.WARNING, logger="chat.live_rooms"):
                with django_capture_on_commit_callbacks(execute=True):
                    g = create_group_room(maya, "Team", ["arjun", "lee"])
        assert Room.objects.filter(pk=g.pk).exists()
        assert sorted(delivered) == sorted([maya.pk, lee.pk])
        [record] = caplog.records
        assert record.levelno == logging.WARNING
        text = record.getMessage()
        assert str(g.id) in text and str(arjun.pk) in text
        assert "arjun" not in text and "Team" not in text

    def test_view_succeeds_when_sends_fail(
        self, client, maya, arjun, django_capture_on_commit_callbacks
    ):
        from unittest import mock

        client.force_login(maya)
        with mock.patch(
            "chat.live_rooms.realtime.send_to_inbox", side_effect=RuntimeError
        ):
            with django_capture_on_commit_callbacks(execute=True):
                response = client.post(
                    reverse("chat:start_group"), {"name": "Team", "members": ["arjun"]}
                )
        assert response.status_code == 302
        assert Room.objects.filter(name="Team").exists()

    def test_failed_summary_build_is_logged(
        self, maya, arjun, caplog, inbox_sends, django_capture_on_commit_callbacks
    ):
        import logging
        from unittest import mock

        from chat.services import create_group_room

        with mock.patch(
            "chat.live_rooms.room_summaries_for_users", side_effect=RuntimeError
        ):
            with caplog.at_level(logging.WARNING, logger="chat.live_rooms"):
                with django_capture_on_commit_callbacks(execute=True):
                    create_group_room(maya, "Team", ["arjun"])
        assert inbox_sends == []
        assert len(caplog.records) == 1

    def test_removed_send_failures_do_not_stop_others(
        self, group, maya, arjun, lee, django_capture_on_commit_callbacks
    ):
        from unittest import mock

        from chat import groups

        delivered = []

        def send(pk, event):
            if pk == maya.pk:
                raise RuntimeError
            delivered.append(pk)

        with mock.patch("chat.live_rooms.realtime.send_to_inbox", side_effect=send):
            with django_capture_on_commit_callbacks(execute=True):
                groups.delete_group(group, maya)
        assert sorted(delivered) == sorted([arjun.pk, lee.pk])

    def test_nothing_sent_when_transaction_rolls_back(
        self, maya, arjun, room, inbox_sends, django_capture_on_commit_callbacks
    ):
        from django.db import transaction

        from chat import live_rooms
        from chat.groups import GroupError

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            with pytest.raises(GroupError):
                with transaction.atomic():
                    live_rooms.room_added(room, [maya, arjun])
                    live_rooms.room_changed(room)
                    live_rooms.room_removed(room.id, [maya.pk])
                    raise GroupError("not_admin")
        assert callbacks == []
        assert inbox_sends == []

    def test_failed_group_change_sends_nothing(
        self, group, arjun, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups

        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(groups.GroupError):
                groups.rename(group, arjun, "Not allowed")
        assert inbox_sends == []


@pytest.mark.django_db
class TestRoomSummariesEndpoint:
    def test_requires_login(self, client):
        response = client.get(reverse("chat:summaries"))
        assert response.status_code == 302

    def test_lists_rooms_most_recent_first(self, client, maya, arjun, room, group):
        from chat.presenters import room_summary

        latest = Message.objects.create(content="newest", room=room, user=arjun)
        latest.visible_for.add(maya, arjun)
        Room.objects.create(name="not mine", type=Room.RoomTypes.GROUP)
        client.force_login(maya)
        data = client.get(reverse("chat:summaries")).json()
        assert [r["id"] for r in data["rooms"]] == [str(room.id), str(group.id)]
        assert data["rooms"][0] == room_summary(maya, room.id)
        assert data["rooms"][1] == room_summary(maya, group.id)

    def test_empty(self, client, maya):
        client.force_login(maya)
        assert client.get(reverse("chat:summaries")).json() == {"rooms": []}

    def test_post_not_allowed(self, client, maya):
        client.force_login(maya)
        assert client.post(reverse("chat:summaries")).status_code == 405

    def test_queries_do_not_grow_with_rooms(self, client, maya, arjun):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(maya)
        counts = []
        for total in (3, 30):
            for i in range(total - Room.objects.count()):
                r = Room.objects.create(name=f"r{i}", type=Room.RoomTypes.GROUP)
                r.members.add(maya, arjun)
                make_messages(r, arjun, 1)
            with CaptureQueriesContext(connection) as ctx:
                rooms = client.get(reverse("chat:summaries")).json()["rooms"]
            assert len(rooms) == total
            counts.append(len(ctx.captured_queries))
        assert counts[0] == counts[1]


@pytest.mark.django_db(transaction=True)
class TestUpdateVisibility:
    """Edits and deletes reach only people who can see the message."""

    async def setup_room(self, maya, arjun, lee):
        from chat.models import Membership
        from chat.services import create_group_room

        def build():
            g = create_group_room(maya, "Team", ["arjun", "lee"])
            message = Message.objects.create(content="secret", room=g, user=maya)
            message.visible_for.add(maya, arjun, lee)
            arjun.visible_for.remove(message)  # arjun cleared his history
            kai = User.objects.create_user("kai", password="pw")
            Membership.objects.create(room=g, user=kai)  # joined after it
            return g, message, kai

        group, message, kai = await database_sync_to_async(build)()
        sockets = {}
        for user in (maya, arjun, lee, kai):
            sockets[user.username] = make_communicator(group.id, user)
            assert (await sockets[user.username].connect())[0]
        return message, sockets

    async def test_edit_and_delete(self, maya, arjun, lee):
        message, sockets = await self.setup_room(maya, arjun, lee)
        for payload in (
            {"type": "edit_message", "id": str(message.id), "message": "edited"},
            {"type": "delete_message", "id": str(message.id)},
        ):
            await sockets["maya"].send_json_to(payload)
            for name in ("maya", "lee"):
                frame = await sockets[name].receive_json_from()
                assert frame["type"] == "message_updated"
                assert frame["id"] == str(message.id)
                assert "visible_to" not in frame
            for name in ("arjun", "kai"):
                assert await sockets[name].receive_nothing(timeout=0.2)
        for socket in sockets.values():
            await socket.disconnect()

    async def test_new_messages_reach_every_member(self, maya, arjun, lee):
        _message, sockets = await self.setup_room(maya, arjun, lee)
        await sockets["lee"].send_json_to({"type": "save_message", "message": "hi"})
        for socket in sockets.values():
            frame = await socket.receive_json_from()
            assert (frame["type"], frame["message"]) == ("save_message", "hi")
            assert "visible_to" not in frame
        for socket in sockets.values():
            await socket.disconnect()

    async def test_cannot_edit_own_cleared_message(self, maya, arjun, room):
        def build():
            message = Message.objects.create(content="old", room=room, user=maya)
            message.visible_for.add(arjun)  # maya cleared it
            return message

        message = await database_sync_to_async(build)()
        maya_socket = make_communicator(room.id, maya)
        arjun_socket = make_communicator(room.id, arjun)
        await maya_socket.connect()
        await arjun_socket.connect()
        await maya_socket.send_json_to(
            {"type": "edit_message", "id": str(message.id), "message": "new"}
        )
        assert (await maya_socket.receive_json_from())["code"] == 403
        assert await arjun_socket.receive_nothing(timeout=0.2)
        await maya_socket.disconnect()
        await arjun_socket.disconnect()

    async def test_removed_member_does_not_get_the_removal_message(
        self, maya, arjun, lee
    ):
        from chat import groups
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(
            maya, "Team", ["arjun", "lee"]
        )
        lee_socket = make_communicator(group.id, lee)
        await lee_socket.connect()
        await database_sync_to_async(groups.remove_member)(group, maya, lee)
        frames = []
        while True:
            output = await lee_socket.receive_output()
            if output["type"] == "websocket.close":
                break
            frames.append(json.loads(output["text"]))
        assert "save_message" not in [f["type"] for f in frames]
        assert frames[-1]["code"] == 403
        await lee_socket.disconnect()


@pytest.mark.django_db(transaction=True)
class TestPingRefreshesContacts:
    async def test_snapshot_after_ping_includes_new_contacts(self, maya, arjun):
        from chat.services import create_group_room

        arjun_inbox = make_inbox(arjun)
        await arjun_inbox.connect()
        await arjun_inbox.receive_json_from()
        maya_inbox = make_inbox(maya)
        await maya_inbox.connect()
        assert (await maya_inbox.receive_json_from())["online"] == []

        await database_sync_to_async(create_group_room)(maya, "Team", ["arjun"])
        await next_frame_of_type(maya_inbox, "room_added")
        await maya_inbox.send_json_to({"type": "ping"})
        snapshot = await next_frame_of_type(maya_inbox, "presence_snapshot")
        assert snapshot["online"] == ["arjun"]
        await maya_inbox.disconnect()
        await arjun_inbox.disconnect()
