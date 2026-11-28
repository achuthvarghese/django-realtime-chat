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
    assert ROOM_UNAVAILABLE.startswith("That chat isn’t available.")
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
        assert ROOM_UNAVAILABLE in response.content.decode()

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

        deleted, cleared, _kept = make_messages(room, arjun, 3)
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
        added = await next_frame_of_type(arjun_inbox, "room_changed")
        assert sorted(added["room"]["member_usernames"]) == ["arjun", "lee", "maya"]
        assert added["room"]["member_count"] == 3

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
        frames = [event["frame"] for _, event in inbox_sends]
        assert frames.count("room_added") == 41
        assert frames.count("room_changed") == 4  # 2 existing members x 2 groups

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

    def test_group_change_failing_after_queuing_sends_nothing(
        self, group, maya, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        """add_members queues room_added (inbox) and the system message and
        room_updated (room) before the last step fails: none of them go out."""
        from unittest import mock

        from chat import groups

        new = User.objects.create_user("kai", password="pw")
        room_sends = []
        with (
            mock.patch(
                "chat.realtime.send_to_room",
                side_effect=lambda r, e: room_sends.append(e),
            ),
            mock.patch(
                "chat.groups.live_rooms.room_changed",
                side_effect=groups.GroupError("too_many"),
            ),
        ):
            with django_capture_on_commit_callbacks(execute=True) as callbacks:
                with pytest.raises(groups.GroupError):
                    groups.add_members(group, maya, ["kai"])
        assert callbacks == []
        assert inbox_sends == [] and room_sends == []
        assert not group.members.filter(pk=new.pk).exists()


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


# Security round (P9c): stale sockets and events after commit


class TestRefusedSocketFrames:
    """A socket refused in connect() is accepted briefly to send the reason;
    frames the client sends before it sees the close are ignored."""

    @pytest.mark.parametrize("room_exists", [False, True])
    def test_frames_on_a_refused_socket_are_ignored(self, room_exists):
        from types import SimpleNamespace

        from chat.channels.consumers import ChatConsumer

        consumer = ChatConsumer()
        consumer.user = SimpleNamespace(pk=1, is_authenticated=True)
        consumer.room = SimpleNamespace() if room_exists else None
        sent = []
        consumer.send = lambda *args, **kwargs: sent.append((args, kwargs))
        consumer.receive(text_data=json.dumps({"type": "read"}))
        consumer.receive(text_data="not json")
        assert sent == []

    def test_room_events_on_a_refused_socket_are_ignored(self):
        from types import SimpleNamespace

        from chat.channels.consumers import ChatConsumer

        consumer = ChatConsumer()
        consumer.user = SimpleNamespace(pk=1, is_authenticated=True)
        sent = []
        consumer.send = lambda *args, **kwargs: sent.append((args, kwargs))
        consumer.close = lambda *args, **kwargs: sent.append(("close", kwargs))
        consumer.membership_revoked({"user_id": 1})
        consumer.room_deleted({})
        consumer.chat_response({"data": {"type": "typing"}})
        assert sent == []


@pytest.mark.django_db(transaction=True)
class TestStaleRoomSocket:
    """A socket whose membership ended without a revoke reaching it (a
    dropped event, or a race) gets nothing that needs membership."""

    async def test_no_updates_after_membership_row_is_gone(self, maya, arjun, lee):
        from chat import groups
        from chat.models import Membership
        from chat.services import create_group_room

        def build():
            g = create_group_room(maya, "Team", ["arjun", "lee"])
            old = Message.objects.create(content="old", room=g, user=maya)
            old.visible_for.add(maya, arjun, lee)
            return g, old

        group, old = await database_sync_to_async(build)()
        lee_socket = make_communicator(group.id, lee)
        maya_socket = make_communicator(group.id, maya)
        assert (await lee_socket.connect())[0]
        assert (await maya_socket.connect())[0]
        await database_sync_to_async(
            Membership.objects.filter(room=group, user=lee).delete
        )()

        await maya_socket.send_json_to(
            {"type": "edit_message", "id": str(old.id), "message": "edited"}
        )
        assert (await maya_socket.receive_json_from())["type"] == "message_updated"
        await maya_socket.send_json_to({"type": "save_message", "message": "new"})
        assert (await maya_socket.receive_json_from())["type"] == "save_message"
        await database_sync_to_async(groups.rename)(group, maya, "Renamed")
        seen_by_maya = [(await maya_socket.receive_json_from())["type"] for _ in "12"]
        assert seen_by_maya == ["save_message", "room_updated"]  # the rename
        assert await lee_socket.receive_nothing(timeout=0.3)
        await lee_socket.disconnect()
        await maya_socket.disconnect()

    async def test_removed_during_connect_is_refused(self, maya, arjun, lee):
        """Removal landing between joining the group and the membership check
        is caught by the check; the socket leaves the group again."""
        from unittest import mock

        from channels.layers import get_channel_layer

        from chat.models import Membership
        from chat.realtime import room_group
        from chat.services import create_group_room

        group = await database_sync_to_async(create_group_room)(
            maya, "Team", ["arjun", "lee"]
        )
        layer = get_channel_layer()
        real_add = layer.group_add

        async def add_then_remove(name, channel):
            await real_add(name, channel)
            await database_sync_to_async(
                Membership.objects.filter(room=group, user=lee).delete
            )()

        socket = make_communicator(group.id, lee)
        with mock.patch.object(layer, "group_add", side_effect=add_then_remove):
            connected, _ = await socket.connect()
        assert connected  # accepted briefly to say why
        assert (await socket.receive_json_from())["code"] == 403
        assert (await socket.receive_output())["code"] == 4403
        assert not layer.groups.get(room_group(group.id))
        await socket.disconnect()


@pytest.mark.django_db(transaction=True)
class TestRoomEventsAfterCommit:
    @pytest.fixture
    def room_sends(self):
        """(event name, still inside a transaction?) for every room send."""
        from unittest import mock

        from django.db import transaction

        from chat import realtime

        sent = []

        def spy(room_id, event):
            sent.append(
                (
                    realtime._event_name(event),
                    transaction.get_connection().in_atomic_block,
                )
            )

        with mock.patch("chat.realtime.send_to_room", side_effect=spy):
            yield sent

    def test_remove_member_order_and_timing(self, group, maya, lee, room_sends):
        from chat import groups

        groups.remove_member(group, maya, lee)
        assert room_sends == [
            ("chat_response/save_message", False),
            ("membership.revoked", False),
            ("chat_response/room_updated", False),
        ]

    def test_leave_with_successor_order(self, maya, arjun, lee, room_sends):
        from chat import groups
        from chat.services import create_group_room

        g = create_group_room(maya, "Team", ["arjun", "lee"])
        room_sends.clear()
        groups.leave(g, maya)
        assert [name for name, _ in room_sends] == [
            "chat_response/save_message",  # left
            "chat_response/save_message",  # is now an admin
            "membership.revoked",
            "chat_response/room_updated",
        ]
        assert not any(inside for _, inside in room_sends)

    def test_delete_after_commit(self, group, maya, room_sends):
        from chat import groups

        groups.delete_group(group, maya)
        assert room_sends == [("room.deleted", False)]

    def test_nothing_sent_on_rollback(self, group, maya, lee, room_sends):
        from django.db import transaction

        from chat import groups

        with pytest.raises(RuntimeError):
            with transaction.atomic():
                groups.rename(group, maya, "Crew")
                groups.remove_member(group, maya, lee)
                raise RuntimeError("later step failed")
        assert room_sends == []
        group.refresh_from_db()
        assert group.name == "Design team"

    def test_failed_send_is_logged_and_others_still_go(self, group, maya, lee, caplog):
        import logging
        from unittest import mock

        sent = []

        def send(room_id, event):
            if event["type"] == "membership.revoked":
                raise RuntimeError(f"layer down for {lee.username}")
            sent.append(event["type"])

        from chat import groups

        with mock.patch("chat.realtime.send_to_room", side_effect=send):
            with caplog.at_level(logging.WARNING, logger="chat.realtime"):
                groups.remove_member(group, maya, lee)
        assert sent == ["chat_response", "chat_response"]
        [record] = caplog.records
        text = record.getMessage()
        assert "membership.revoked" in text and str(group.id) in text
        assert "lee" not in text

    def test_room_updated_goes_to_current_members(self, group, maya, lee):
        from unittest import mock

        from chat import groups

        events = []
        with mock.patch(
            "chat.realtime.send_to_room", side_effect=lambda r, e: events.append(e)
        ):
            groups.remove_member(group, maya, lee)
        [updated] = [
            e for e in events if e.get("data", {}).get("type") == "room_updated"
        ]
        assert sorted(updated["visible_to"]) == sorted(
            group.members.values_list("pk", flat=True)
        )
        assert lee.pk not in updated["visible_to"]


# Review round 1 (P9c): set-based summaries, room_changed on membership
# changes, logging, races


def timed_message(room, user, text, at, kind=Message.Kinds.TEXT, visible=None):
    message = Message.objects.create(content=text, room=room, user=user, kind=kind)
    Message.objects.filter(pk=message.pk).update(created_at=at)
    message.visible_for.add(*(visible if visible is not None else room.members.all()))
    return message


@pytest.mark.django_db
class TestRoomSummariesForUsersRich:
    def test_equal_to_room_summary_with_history(self, maya, arjun, lee):
        from datetime import timedelta

        from django.utils import timezone

        from chat.models import ReadState
        from chat.presenters import room_summaries_for_users, room_summary
        from chat.services import create_group_room

        outsider = User.objects.create_user("zed", password="pw")
        g = create_group_room(maya, "Team", ["arjun", "lee"])
        now = timezone.now()
        timed_message(g, arjun, "a1", now - timedelta(minutes=5))
        timed_message(g, maya, "m1", now - timedelta(minutes=4))
        # arjun cleared this one
        timed_message(g, lee, "l1", now - timedelta(minutes=3), visible=[lee, maya])
        deleted = timed_message(g, arjun, "gone", now - timedelta(minutes=2))
        Message.objects.filter(pk=deleted.pk).update(deleted_at=now)
        timed_message(
            g, arjun, "sys", now - timedelta(minutes=1), kind=Message.Kinds.SYSTEM
        )
        ReadState.objects.create(
            user=lee, room=g, last_read_at=now - timedelta(minutes=4, seconds=30)
        )
        ReadState.objects.create(user=arjun, room=g, last_read_at=now)

        got = room_summaries_for_users(g.id, [maya, arjun, lee, outsider])
        assert outsider.pk not in got
        for user in (maya, arjun, lee):
            assert got[user.pk] == room_summary(user, g.id), user.username
        assert (got[maya.pk]["last_content"], got[maya.pk]["unread"]) == ("l1", 2)
        assert (got[arjun.pk]["last_content"], got[arjun.pk]["unread"]) == ("m1", 0)
        assert (got[lee.pk]["last_content"], got[lee.pk]["unread"]) == ("l1", 1)

        direct = Room.objects.create(name="x", type=Room.RoomTypes.PRIVATE)
        direct.members.add(maya, arjun)
        timed_message(direct, maya, "hi", now)
        got = room_summaries_for_users(direct.id, [maya, arjun])
        for user in (maya, arjun):
            assert got[user.pk] == room_summary(user, direct.id)

    def test_same_time_messages_pick_only_what_you_can_see(self, maya, arjun, room):
        from django.utils import timezone

        from chat.presenters import room_summaries_for_users, room_summary

        now = timezone.now()
        timed_message(room, maya, "for both", now, visible=[maya, arjun])
        timed_message(room, arjun, "arjun only", now, visible=[arjun])
        got = room_summaries_for_users(room.id, [maya, arjun])
        assert got[maya.pk]["last_content"] == "for both"
        for user in (maya, arjun):
            assert got[user.pk] == room_summary(user, room.id)

    def test_queries_do_not_grow_with_history(self, maya, arjun, lee):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat import presence
        from chat.presenters import room_summaries_for_users
        from chat.services import create_group_room

        people = make_users("p", 10)
        g = create_group_room(maya, "Team", ["arjun", "lee"])
        presence.mark_read(lee, g)
        counts = []
        for total in (5, 200):
            make_messages(g, arjun, total - Message.objects.filter(room=g).count())
            from chat.models import Membership

            Membership.objects.bulk_create(
                [Membership(room=g, user=u) for u in people if not u.rooms.exists()]
            )
            with CaptureQueriesContext(connection) as ctx:
                got = room_summaries_for_users(g.id, [maya, arjun, lee, *people])
            assert len(got) == 13
            counts.append(len(ctx.captured_queries))
        assert counts[0] == counts[1]


@pytest.mark.django_db
class TestRoomChangedOnMembership:
    @staticmethod
    def frame_type(event):
        return event.get("frame") or event["type"].removeprefix("inbox.")

    def frames(self, sends, frame):
        return [(pk, e["room"]) for pk, e in sends if self.frame_type(e) == frame]

    def test_add_tells_existing_members_only(
        self, group, maya, arjun, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups

        kai = User.objects.create_user("kai", password="pw")
        with django_capture_on_commit_callbacks(execute=True):
            groups.add_members(group, arjun, ["kai"])
        changed = self.frames(inbox_sends, "room_changed")
        assert sorted(pk for pk, _ in changed) == sorted([maya.pk, arjun.pk, lee.pk])
        room = changed[0][1]
        assert set(room) == {
            "id",
            "title",
            "initials",
            "member_count",
            "member_usernames",
        }
        assert sorted(room["member_usernames"]) == ["arjun", "kai", "lee", "maya"]
        assert room["member_count"] == 4
        assert [pk for pk, _ in self.frames(inbox_sends, "room_added")] == [kai.pk]

    def test_remove_tells_remaining_members(
        self, group, maya, arjun, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups

        with django_capture_on_commit_callbacks(execute=True):
            groups.remove_member(group, maya, lee)
        changed = self.frames(inbox_sends, "room_changed")
        assert sorted(pk for pk, _ in changed) == sorted([maya.pk, arjun.pk])
        assert sorted(changed[0][1]["member_usernames"]) == ["arjun", "maya"]
        assert [pk for pk, _ in self.frames(inbox_sends, "room_removed")] == [lee.pk]

    def test_leave_tells_remaining_members(
        self, group, maya, arjun, lee, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups

        with django_capture_on_commit_callbacks(execute=True):
            groups.leave(group, arjun)
        changed = self.frames(inbox_sends, "room_changed")
        assert sorted(pk for pk, _ in changed) == sorted([maya.pk, lee.pk])
        assert changed[0][1]["member_count"] == 2

    def test_last_member_leaving_sends_no_room_changed(
        self, maya, arjun, inbox_sends, django_capture_on_commit_callbacks
    ):
        from chat import groups
        from chat.services import create_group_room

        g = create_group_room(maya, "Team", ["arjun"])
        groups.leave(g, arjun)
        with django_capture_on_commit_callbacks(execute=True):
            groups.leave(g, maya)
        assert [self.frame_type(e) for _, e in inbox_sends] == ["room_removed"]


@pytest.mark.django_db
class TestLiveRoomLogging:
    def test_one_warning_per_action_with_count(
        self, group, maya, arjun, lee, caplog, django_capture_on_commit_callbacks
    ):
        import logging
        from unittest import mock

        from chat import groups

        with mock.patch(
            "chat.live_rooms.realtime.send_to_inbox", side_effect=RuntimeError
        ):
            with caplog.at_level(logging.WARNING, logger="chat.live_rooms"):
                with django_capture_on_commit_callbacks(execute=True):
                    groups.rename(group, maya, "Crew")
        [record] = caplog.records
        text = record.getMessage()
        assert "room_changed" in text and "3 of 3" in text
        assert "Crew" not in text and "maya" not in text

    def test_build_failure_logs_traceback(
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
                    g = create_group_room(maya, "Team", ["arjun"])
        [record] = caplog.records
        assert record.exc_info is not None
        assert str(g.id) in record.getMessage()


@pytest.mark.django_db
class TestChatPageRace:
    def test_removed_between_queries_redirects(self, client, maya, room):
        from unittest import mock

        from chat.views import ROOM_UNAVAILABLE

        client.force_login(maya)
        with mock.patch("chat.views.rooms_for", return_value=[]):
            response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.status_code == 302
        assert response.url == reverse("chat:chat")
        from django.contrib.messages import get_messages

        assert [m.message for m in get_messages(response.wsgi_request)] == [
            ROOM_UNAVAILABLE
        ]


# User-tester round (P9c): room_refresh, busy database, leave notice


@pytest.mark.django_db(transaction=True)
class TestRoomRefresh:
    """Edits and deletes ask the room lists of people who can see the
    message (and are still members) to refetch that room."""

    async def build(self, maya, arjun, lee):
        from chat.models import Membership
        from chat.services import create_group_room

        def setup():
            g = create_group_room(maya, "Team", ["arjun", "lee"])
            message = Message.objects.create(content="secret", room=g, user=maya)
            message.visible_for.add(maya, arjun, lee)
            arjun.visible_for.remove(message)  # arjun cleared it
            kai = User.objects.create_user("kai", password="pw")
            Membership.objects.create(room=g, user=kai)  # joined after it
            eve = User.objects.create_user("eve", password="pw")
            Membership.objects.create(room=g, user=eve)
            message.visible_for.add(eve)
            Membership.objects.filter(room=g, user=eve).delete()  # left, no revoke
            return g, message

        return await database_sync_to_async(setup)()

    async def test_sent_only_to_members_who_can_see_it(self, maya, arjun, lee):
        from unittest import mock

        group, message = await self.build(maya, arjun, lee)
        sent = []
        socket = make_communicator(group.id, maya)
        await socket.connect()
        with mock.patch(
            "chat.live_rooms.realtime.send_to_inbox",
            side_effect=lambda pk, event: sent.append((pk, event)),
        ):
            for payload in (
                {"type": "edit_message", "id": str(message.id), "message": "new"},
                {"type": "delete_message", "id": str(message.id)},
            ):
                await socket.send_json_to(payload)
                assert (await socket.receive_json_from())["type"] == "message_updated"
        await socket.disconnect()
        event = {"type": "inbox.room_refresh", "room": str(group.id)}
        assert sorted(sent) == sorted(
            [(maya.pk, event), (lee.pk, event), (maya.pk, event), (lee.pk, event)]
        )

    async def test_inbox_receives_room_refresh(self, maya, arjun, lee):
        group, message = await self.build(maya, arjun, lee)
        inbox = make_inbox(lee)
        await inbox.connect()
        socket = make_communicator(group.id, maya)
        await socket.connect()
        await socket.send_json_to({"type": "delete_message", "id": str(message.id)})
        frame = await next_frame_of_type(inbox, "room_refresh")
        assert frame == {"type": "room_refresh", "room": str(group.id)}
        await socket.disconnect()
        await inbox.disconnect()

    async def test_failed_refresh_send_keeps_the_edit(self, maya, arjun, lee, caplog):
        import logging
        from unittest import mock

        group, message = await self.build(maya, arjun, lee)
        socket = make_communicator(group.id, maya)
        await socket.connect()
        with mock.patch(
            "chat.live_rooms.realtime.send_to_inbox", side_effect=RuntimeError
        ):
            with caplog.at_level(logging.WARNING, logger="chat.live_rooms"):
                await socket.send_json_to(
                    {"type": "edit_message", "id": str(message.id), "message": "x"}
                )
                assert (await socket.receive_json_from())["message"] == "x"
        assert any("room_refresh" in r.getMessage() for r in caplog.records)
        await socket.send_json_to({"type": "save_message", "message": "still open"})
        assert (await socket.receive_json_from())["message"] == "still open"
        await socket.disconnect()


@pytest.mark.django_db(transaction=True)
class TestBusyDatabase:
    async def test_read_survives_locked_database(self, maya, room, caplog):
        import logging
        from unittest import mock

        from django.db import OperationalError

        socket = make_communicator(room.id, maya)
        await socket.connect()
        with mock.patch(
            "chat.channels.consumers.presence.mark_read",
            side_effect=OperationalError("database is locked"),
        ):
            with caplog.at_level(logging.WARNING, logger="chat.channels.consumers"):
                await socket.send_json_to({"type": "read"})
                assert await socket.receive_nothing(timeout=0.3)
        [record] = caplog.records
        assert str(room.id) in record.getMessage()
        assert "locked" not in record.getMessage()
        await socket.send_json_to({"type": "save_message", "message": "hi"})
        assert (await socket.receive_json_from())["message"] == "hi"
        await socket.disconnect()

    def test_sqlite_waits_for_locks(self):
        from django.conf import settings

        db = settings.DATABASES["default"]
        assert db["ENGINE"] == "django.db.backends.sqlite3"
        assert db["OPTIONS"]["timeout"] == 20
        assert db["OPTIONS"]["transaction_mode"] == "IMMEDIATE"


@pytest.mark.django_db
class TestLeaveNotice:
    def test_json_leave_queues_the_notice(self, client, group, arjun):
        from django.contrib.messages import SUCCESS, get_messages

        client.force_login(arjun)
        response = client.post(
            reverse("chat:group_action", args=[group.id, "leave"]),
            HTTP_ACCEPT="application/json",
        )
        assert response.json() == {"ok": True, "redirect": reverse("chat:chat")}
        notices = [(m.level, m.message) for m in get_messages(response.wsgi_request)]
        assert notices == [(SUCCESS, "You left Design team.")]

    def test_redirect_leave_has_same_notice(self, client, group, arjun):
        from django.contrib.messages import get_messages

        client.force_login(arjun)
        response = client.post(reverse("chat:group_action", args=[group.id, "leave"]))
        assert [m.message for m in get_messages(response.wsgi_request)] == [
            "You left Design team."
        ]

    def test_other_json_actions_add_no_notice(self, client, group, maya):
        from django.contrib.messages import get_messages

        client.force_login(maya)
        response = client.post(
            reverse("chat:group_action", args=[group.id, "rename"]),
            {"name": "Crew"},
            HTTP_ACCEPT="application/json",
        )
        assert response.json()["ok"] is True
        assert list(get_messages(response.wsgi_request)) == []


# Replies (P10a)


def visible_text(room, user, text, visible=None):
    """A text message from `user`, visible to `visible` (default: members)."""
    message = Message.objects.create(content=text, room=room, user=user)
    message.visible_for.add(*(visible if visible is not None else room.members.all()))
    return message


def reply(room, user, original, text="re", visible=None):
    message = Message.objects.create(
        content=text, room=room, user=user, reply_to=original
    )
    message.visible_for.add(*(visible if visible is not None else room.members.all()))
    return message


@pytest.mark.django_db(transaction=True)
class TestReplyMigration:
    def test_migration_applies_and_reverses(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        def columns():
            with connection.cursor() as cursor:
                return {
                    c.name
                    for c in connection.introspection.get_table_description(
                        cursor, "chat_message"
                    )
                }

        executor = MigrationExecutor(connection)
        executor.migrate([("chat", "0004_group_admins")])
        assert "reply_to_id" not in columns()
        executor = MigrationExecutor(connection)
        executor.migrate([("chat", "0005_message_reply_to")])
        assert "reply_to_id" in columns()
        # Back to the latest schema so later tests see every table.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
class TestReplyConstraints:
    def test_system_messages_cannot_reply(self, maya, room):
        from django.db import IntegrityError, transaction

        original = visible_text(room, maya, "hi")
        with pytest.raises(IntegrityError), transaction.atomic():
            Message.objects.create(
                content="x",
                room=room,
                user=maya,
                kind=Message.Kinds.SYSTEM,
                reply_to=original,
            )

    def test_message_cannot_reply_to_itself(self, maya, room):
        from django.db import IntegrityError, transaction

        message = visible_text(room, maya, "hi")
        with pytest.raises(IntegrityError), transaction.atomic():
            Message.objects.filter(pk=message.pk).update(reply_to=message.pk)

    def test_original_removed_from_db_makes_reply_plain(self, maya, arjun, room):
        from chat.presenters import message_data

        original = visible_text(room, arjun, "hi")
        answer = reply(room, maya, original)
        arjun.delete()  # cascades to arjun's messages
        answer.refresh_from_db()
        assert answer.reply_to_id is None
        assert message_data(answer)["reply_to"] is None


@pytest.mark.django_db
class TestReplyPresenter:
    def test_plain_message(self, maya, room):
        from chat.presenters import message_data

        assert message_data(visible_text(room, maya, "hi"))["reply_to"] is None

    def test_visible_original(self, maya, arjun, room):
        from chat.presenters import message_data

        arjun.first_name = "Arjun"
        arjun.save()
        original = visible_text(room, arjun, "  line one\n\n\tline   two  " + "x" * 300)
        data = message_data(reply(room, maya, original), reply_visible=True)
        quote = data["reply_to"]
        assert quote == {
            "id": str(original.id),
            "available": True,
            "deleted": False,
            "user": "arjun",
            "name": "Arjun",
            "excerpt": ("line one line two " + "x" * 300)[:200],
        }
        assert len(quote["excerpt"]) == 200

    def test_deleted_original(self, maya, arjun, room):
        from django.utils import timezone

        from chat.presenters import message_data

        original = visible_text(room, arjun, "secret")
        answer = reply(room, maya, original)
        Message.objects.filter(pk=original.pk).update(
            content="", deleted_at=timezone.now()
        )
        answer = Message.objects.select_related("reply_to__user").get(pk=answer.pk)
        assert message_data(answer, reply_visible=True)["reply_to"] == {
            "id": str(original.id),
            "available": True,
            "deleted": True,
            "user": "arjun",
            "name": "arjun",
        }

    def test_unavailable_original_and_safe_default(self, maya, arjun, room):
        from chat.presenters import message_data

        original = visible_text(room, arjun, "secret")
        answer = reply(room, maya, original)
        expected = {"id": str(original.id), "available": False}
        assert message_data(answer, reply_visible=False)["reply_to"] == expected
        assert message_data(answer)["reply_to"] == expected  # no annotation

    def test_deleted_reply_has_no_quote(self, maya, arjun, room):
        from django.utils import timezone

        from chat.presenters import message_data

        answer = reply(room, maya, visible_text(room, arjun, "hi"))
        answer.deleted_at = timezone.now()
        assert message_data(answer, reply_visible=True)["reply_to"] is None


@pytest.mark.django_db
class TestReplyHistory:
    def test_history_carries_per_viewer_quotes(self, client, maya, arjun, lee, group):
        original = visible_text(group, maya, "before lee", visible=[maya, arjun])
        answer = reply(group, arjun, original, "answer")
        for user, available in ((arjun, True), (lee, False)):
            client.force_login(user)
            data = client.get(reverse("chat:history", args=[group.id])).json()
            row = next(m for m in data["messages"] if m["id"] == str(answer.id))
            assert row["reply_to"]["available"] is available
            if not available:
                assert row["reply_to"] == {"id": str(original.id), "available": False}
            else:
                assert row["reply_to"]["excerpt"] == "before lee"

    def test_initial_page_carries_quotes(self, client, maya, arjun, room):
        original = visible_text(room, arjun, "question")
        answer = reply(room, maya, original, "answer")
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": room.id})
        row = next(
            m for m in response.context["room_messages"] if m["id"] == str(answer.id)
        )
        assert row["reply_to"]["excerpt"] == "question"
        assert row["reply_to"]["available"] is True

    def test_history_queries_do_not_grow_with_replies(self, client, maya, arjun, room):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(maya)
        url = reverse("chat:history", args=[room.id])
        counts = []
        for total in (1, 20):
            while Message.objects.filter(room=room).count() < total * 2:
                users = (maya, arjun)
                n = Message.objects.count()
                original = visible_text(room, users[n % 2], f"q{n}")
                reply(room, users[(n + 1) % 2], original, f"a{n}")
            with CaptureQueriesContext(connection) as ctx:
                assert client.get(url).status_code == 200
            counts.append(len(ctx.captured_queries))
        assert counts[0] == counts[1]


@pytest.mark.django_db(transaction=True)
class TestReplySockets:
    async def connect(self, room, *users):
        sockets = []
        for user in users:
            socket = make_communicator(room.id, user)
            assert (await socket.connect())[0]
            sockets.append(socket)
        return sockets

    async def close(self, *sockets):
        for socket in sockets:
            await socket.disconnect()

    async def test_reply_is_saved_and_quoted(self, maya, arjun, room):
        original = await database_sync_to_async(visible_text)(room, arjun, "q?")
        maya_socket, arjun_socket = await self.connect(room, maya, arjun)
        await maya_socket.send_json_to(
            {"type": "save_message", "message": "yes", "reply_to": str(original.id)}
        )
        for socket in (maya_socket, arjun_socket):
            frame = await socket.receive_json_from()
            assert frame["type"] == "save_message"
            assert frame["reply_to"]["excerpt"] == "q?"
            assert frame["reply_to"]["id"] == str(original.id)
        saved = await database_sync_to_async(Message.objects.get)(content="yes")
        assert saved.reply_to_id == original.id
        await self.close(maya_socket, arjun_socket)

    async def test_plain_message_has_null_reply(self, maya, room):
        (socket,) = await self.connect(room, maya)
        await socket.send_json_to({"type": "save_message", "message": "hi"})
        assert (await socket.receive_json_from())["reply_to"] is None
        await self.close(socket)

    async def test_rejected_targets(self, maya, arjun, lee, room):
        from django.utils import timezone

        def build():
            other = Room.objects.create(name="other", type=Room.RoomTypes.PRIVATE)
            other.members.add(maya, lee)
            elsewhere = visible_text(other, lee, "elsewhere")
            system = Message.objects.create(
                content="event", room=room, user=arjun, kind=Message.Kinds.SYSTEM
            )
            system.visible_for.add(maya, arjun)
            deleted = visible_text(room, arjun, "gone")
            Message.objects.filter(pk=deleted.pk).update(
                content="", deleted_at=timezone.now()
            )
            hidden = visible_text(room, arjun, "cleared", visible=[arjun])
            return [elsewhere.id, system.id, deleted.id, hidden.id]

        ids = await database_sync_to_async(build)()
        maya_socket, arjun_socket = await self.connect(room, maya, arjun)
        targets = [str(i) for i in ids] + [
            "not-a-uuid",
            "00000000-0000-0000-0000-000000000000",
            123,
            {"id": str(ids[0])},
            "",
        ]
        for target in targets:
            await maya_socket.send_json_to(
                {"type": "save_message", "message": "x", "reply_to": target}
            )
            frame = await maya_socket.receive_json_from()
            assert (frame["type"], frame["code"], frame["message"]) == (
                "error",
                400,
                "You can't reply to that message",
            ), target
        assert await arjun_socket.receive_nothing(timeout=0.2)
        count = await database_sync_to_async(
            Message.objects.filter(content="x").count
        )()
        assert count == 0
        await self.close(maya_socket, arjun_socket)

    async def test_vanished_target_is_refused(self, maya, arjun, room, monkeypatch):
        from django.db import IntegrityError

        from chat.channels import consumers

        original = await database_sync_to_async(visible_text)(room, arjun, "q")

        def boom(*args, **kwargs):
            raise IntegrityError("FOREIGN KEY constraint failed")

        monkeypatch.setattr(consumers.Message.objects, "create", boom)
        (socket,) = await self.connect(room, maya)
        await socket.send_json_to(
            {"type": "save_message", "message": "x", "reply_to": str(original.id)}
        )
        frame = await socket.receive_json_from()
        assert frame["message"] == "You can't reply to that message"
        await self.close(socket)

    async def setup_split(self, maya, arjun, lee):
        """A group where kai joined after `original`, so kai can't see it."""
        from chat.models import Membership
        from chat.services import create_group_room

        def build():
            g = create_group_room(maya, "Team", ["arjun", "lee"])
            original = visible_text(g, maya, "private plan")
            kai = User.objects.create_user("kai", password="pw")
            Membership.objects.create(room=g, user=kai)
            return g, original, kai

        return await database_sync_to_async(build)()

    async def test_new_reply_split_by_who_sees_original(self, maya, arjun, lee):
        group, original, kai = await self.setup_split(maya, arjun, lee)
        sockets = await self.connect(group, maya, arjun, lee, kai)
        await sockets[1].send_json_to(
            {"type": "save_message", "message": "ok", "reply_to": str(original.id)}
        )
        for socket in sockets[:3]:
            frame = await socket.receive_json_from()
            assert frame["reply_to"]["excerpt"] == "private plan"
        frame = await sockets[3].receive_output()
        assert "private plan" not in frame["text"]
        data = json.loads(frame["text"])
        assert data["message"] == "ok"
        assert data["reply_to"] == {"id": str(original.id), "available": False}
        for socket in sockets:
            assert await socket.receive_nothing(timeout=0.1)
        await self.close(*sockets)

    async def test_reply_edit_split_and_keeps_target(self, maya, arjun, lee):
        group, original, kai = await self.setup_split(maya, arjun, lee)

        def make_reply():
            members = list(group.members.all())
            return reply(group, arjun, original, "first", visible=members)

        answer = await database_sync_to_async(make_reply)()
        sockets = await self.connect(group, maya, arjun, lee, kai)
        await sockets[1].send_json_to(
            {
                "type": "edit_message",
                "id": str(answer.id),
                "message": "second",
                "reply_to": None,
            }
        )
        for socket in sockets[:3]:
            frame = await socket.receive_json_from()
            assert frame["type"] == "message_updated"
            assert frame["reply_to"]["excerpt"] == "private plan"
        output = await sockets[3].receive_output()
        assert "private plan" not in output["text"]
        frame = json.loads(output["text"])
        assert (frame["type"], frame["message"]) == ("message_updated", "second")
        assert frame["reply_to"] == {"id": str(original.id), "available": False}
        await database_sync_to_async(answer.refresh_from_db)()
        assert answer.reply_to_id == original.id
        await self.close(*sockets)

    async def test_inbox_activity_has_null_reply(self, maya, arjun, room):
        original = await database_sync_to_async(visible_text)(room, arjun, "q")
        inbox = make_inbox(arjun)
        await inbox.connect()
        await inbox.receive_json_from()  # presence snapshot
        (socket,) = await self.connect(room, maya)
        await socket.send_json_to(
            {"type": "save_message", "message": "a", "reply_to": str(original.id)}
        )
        frame = await next_frame_of_type(inbox, "room_activity")
        assert frame["message"]["reply_to"] is None
        await self.close(socket, inbox)


@pytest.mark.django_db
class TestReplyDemoData:
    @pytest.fixture(autouse=True)
    def seeded(self, settings):
        from django.core.management import call_command

        settings.DEBUG = True
        call_command("seed_demo", stdout=__import__("io").StringIO())

    def test_seeded_chats_have_replies(self):
        replies = Message.objects.exclude(reply_to=None).select_related("reply_to")
        rooms = {m.room.type for m in replies.select_related("room")}
        assert rooms == {Room.RoomTypes.GROUP, Room.RoomTypes.PRIVATE}
        for m in replies:
            assert m.reply_to.room_id == m.room_id
            assert m.reply_to.created_at < m.created_at

    def test_priya_cannot_see_the_quoted_original(self, client):
        priya = User.objects.get(username="priya")
        books = Room.objects.get(name="Book club")
        client.force_login(priya)
        data = client.get(reverse("chat:history", args=[books.id])).json()
        quoted = [m["reply_to"] for m in data["messages"] if m["reply_to"]]
        assert quoted and all(set(q) == {"id", "available"} for q in quoted)
        assert not any(q["available"] for q in quoted)
        client.force_login(User.objects.get(username="maya"))
        data = client.get(reverse("chat:history", args=[books.id])).json()
        quoted = [m["reply_to"] for m in data["messages"] if m["reply_to"]]
        assert [q["excerpt"] for q in quoted] == [
            "Next pick: The Left Hand of Darkness?"
        ]


@pytest.mark.django_db
class TestReplyReviewFixes:
    def test_history_cursor_must_be_visible(self, client, maya, arjun, room):
        hidden = visible_text(room, arjun, "cleared", visible=[arjun])
        client.force_login(maya)
        url = reverse("chat:history", args=[room.id])
        for before in (hidden.id, "00000000-0000-0000-0000-000000000000"):
            response = client.get(url, {"before": before})
            assert response.status_code == 400
            assert response.json() == {"error": "Unknown message"}

    def test_cross_room_reply_never_quotes(self, client, maya, arjun, room):
        from chat.presenters import message_data

        other = Room.objects.create(name="other", type=Room.RoomTypes.PRIVATE)
        other.members.add(maya, arjun)
        elsewhere = visible_text(other, arjun, "other room secret")
        stray = reply(room, maya, elsewhere, "stray")  # bypasses the socket check
        client.force_login(maya)
        data = client.get(reverse("chat:history", args=[room.id])).json()
        row = next(m for m in data["messages"] if m["id"] == str(stray.id))
        assert row["reply_to"] == {"id": str(elsewhere.id), "available": False}
        assert message_data(stray, reply_visible=True)["reply_to"]["available"] is False

    def test_history_loads_only_shown_user_fields(self, client, maya, arjun, room):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        reply(room, maya, visible_text(room, arjun, "q"), "a")
        client.force_login(maya)
        with CaptureQueriesContext(connection) as ctx:
            data = client.get(reverse("chat:history", args=[room.id])).json()
        history_sql = [q["sql"] for q in ctx.captured_queries if "reply_to" in q["sql"]]
        assert history_sql and not any("password" in q for q in history_sql)
        assert data["messages"][1]["reply_to"]["excerpt"] == "q"
        assert data["messages"][1]["name"] == "maya"

    def test_one_reply_constraint(self):
        names = [c.name for c in Message._meta.constraints]
        assert names == ["message_reply_valid"]


@pytest.mark.django_db(transaction=True)
class TestReplyReviewSockets:
    async def test_errors_say_which_frame_they_answer(self, maya, arjun, room):
        original = await database_sync_to_async(visible_text)(room, arjun, "q")
        socket = make_communicator(room.id, maya)
        await socket.connect()
        cases = [
            ({"type": "save_message", "message": "x", "reply_to": ""}, "save_message"),
            ({"type": "save_message", "message": " "}, "save_message"),
            (
                {"type": "edit_message", "id": str(original.id), "message": "x"},
                "edit_message",
            ),
            ({"type": "delete_message", "id": str(original.id)}, "delete_message"),
        ]
        for payload, frame_for in cases:
            await socket.send_json_to(payload)
            frame = await socket.receive_json_from()
            assert (frame["type"], frame["for"]) == ("error", frame_for)
        await socket.send_json_to({"type": "nope"})
        assert "for" not in await socket.receive_json_from()
        await socket.disconnect()

    async def test_editing_an_original_keeps_its_shape(self, maya, arjun, room):
        def build():
            original = visible_text(room, maya, "q")
            reply(room, arjun, original, "a")
            return original

        original = await database_sync_to_async(build)()
        socket = make_communicator(room.id, maya)
        await socket.connect()
        await socket.send_json_to(
            {"type": "edit_message", "id": str(original.id), "message": "q2"}
        )
        frame = await socket.receive_json_from()
        assert set(frame) == {
            "type",
            "id",
            "message",
            "user",
            "name",
            "initials",
            "created_at",
            "edited",
            "deleted",
            "kind",
            "reply_to",
            "reactions",
            "mentions",
        }
        assert (frame["type"], frame["message"], frame["edited"]) == (
            "message_updated",
            "q2",
            True,
        )
        assert frame["reply_to"] is None
        await socket.disconnect()


@pytest.mark.django_db
class TestReplyDemoDeleted:
    def test_ops_reply_quotes_a_deleted_message(self, client, settings):
        from io import StringIO

        from django.core.management import call_command

        settings.DEBUG = True
        call_command("seed_demo", stdout=StringIO())
        ops = Room.objects.get(name="Ops")
        client.force_login(User.objects.get(username="maya"))
        data = client.get(reverse("chat:history", args=[ops.id])).json()
        quotes = [m["reply_to"] for m in data["messages"] if m["reply_to"]]
        deleted = [q for q in quotes if q["available"] and q["deleted"]]
        assert len(deleted) == 1 and "excerpt" not in deleted[0]
        assert deleted[0]["user"] == "sofia"


# Reactions (P10b)


def react(message, user, emoji, at=None):
    from chat.models import Reaction

    reaction = Reaction.objects.create(message=message, user=user, emoji=emoji)
    if at is not None:
        Reaction.objects.filter(pk=reaction.pk).update(created_at=at)
    return reaction


@pytest.fixture(autouse=True)
def fresh_react_limits():
    """Rate-limit windows live in the cache and are keyed by user pk, which
    tests reuse; start every test with none."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


CANT_REACT_FRAME = {
    "type": "error",
    "code": 400,
    "message": "You can't react to that message",
    "for": "react",
}


def without_ts(frame):
    return {k: v for k, v in frame.items() if k != "ts"}


@pytest.mark.django_db
class TestReactionModel:
    def test_one_of_each_emoji_per_person(self, maya, room):
        from django.db import IntegrityError, transaction

        message = visible_text(room, maya, "hi")
        react(message, maya, "heart")
        react(message, maya, "party")  # another emoji is fine
        with pytest.raises(IntegrityError), transaction.atomic():
            react(message, maya, "heart")

    def test_only_known_emoji(self, maya, room):
        from django.db import IntegrityError, transaction

        message = visible_text(room, maya, "hi")
        with pytest.raises(IntegrityError), transaction.atomic():
            react(message, maya, "skull")

    def test_removed_with_message_and_kept_when_reactor_leaves(
        self, maya, arjun, lee, group
    ):
        from chat import groups
        from chat.models import Reaction

        message = visible_text(group, maya, "hi")
        react(message, lee, "heart")
        groups.leave(group, lee)
        assert Reaction.objects.filter(message=message, user=lee).exists()
        message.delete()
        assert not Reaction.objects.exists()

    def test_emoji_table(self):
        from chat.presenters import reaction_emoji_table

        table = reaction_emoji_table()
        assert [r["key"] for r in table] == [
            "thumbs_up",
            "heart",
            "laugh",
            "wow",
            "sad",
            "party",
        ]
        assert table[0] == {"key": "thumbs_up", "char": "👍", "label": "Thumbs up"}
        assert table[1]["char"] == "❤️"
        assert [r["label"] for r in table[2:]] == [
            "Laughing",
            "Surprised",
            "Sad",
            "Party",
        ]


@pytest.mark.django_db
class TestReactionPayload:
    def test_emoji_in_fixed_order_and_people_by_time(self, maya, arjun, lee, group):
        from datetime import timedelta

        from django.utils import timezone

        from chat.presenters import reactions_for_messages

        maya.first_name, maya.last_name = "Maya", "Rao"
        maya.save()
        message = visible_text(group, maya, "hi")
        t = timezone.now()
        react(message, lee, "party", t)
        react(message, maya, "party", t - timedelta(seconds=5))
        react(message, arjun, "thumbs_up", t + timedelta(seconds=5))
        assert reactions_for_messages([message.pk]) == {
            message.pk: [
                {
                    "emoji": "thumbs_up",
                    "count": 1,
                    "users": [{"user": "arjun", "name": "arjun"}],
                },
                {
                    "emoji": "party",
                    "count": 2,
                    "users": [
                        {"user": "maya", "name": "Maya Rao"},
                        {"user": "lee", "name": "Lee"},
                    ],
                },
            ]
        }

    def test_deleted_system_and_new_messages_have_none(self, maya, room):
        from chat.presenters import message_data, reactions_for_message

        message = visible_text(room, maya, "hi")
        assert message_data(message)["reactions"] == []
        react(message, maya, "heart")
        listed = reactions_for_message(message)
        assert len(listed) == 1
        assert message_data(message, reactions=listed)["reactions"] == listed
        system = Message.objects.create(
            content="x", room=room, user=maya, kind=Message.Kinds.SYSTEM
        )
        assert message_data(system, reactions=listed)["reactions"] == []
        from django.utils import timezone

        message.deleted_at = timezone.now()
        assert message_data(message, reactions=listed)["reactions"] == []
        assert reactions_for_message(message) == []

    def test_matches_building_from_model_objects(self, maya, arjun, lee, group):
        from chat.models import Reaction, ReactionEmoji
        from chat.presenters import display_name, reactions_for_messages

        arjun.first_name, arjun.last_name = "Arjun", "Kumar"
        arjun.save()
        messages = [visible_text(group, maya, f"m{i}") for i in range(4)]
        people = [maya, arjun, lee]
        for i, m in enumerate(messages[:3]):
            for j, emoji in enumerate(ReactionEmoji.values[i:]):
                react(m, people[(i + j) % 3], emoji)
                if j % 2:
                    react(m, people[(i + j + 1) % 3], emoji)

        # The plain model-object way to build the same data.
        expected = {}
        order = list(ReactionEmoji.values)
        for r in Reaction.objects.select_related("user").order_by("created_at", "id"):
            per = expected.setdefault(r.message_id, {})
            per.setdefault(r.emoji, []).append(
                {"user": r.user.username, "name": display_name(r.user)}
            )
        expected = {
            mid: [
                {"emoji": e, "count": len(u), "users": u}
                for e, u in sorted(per.items(), key=lambda kv: order.index(kv[0]))
            ]
            for mid, per in expected.items()
        }
        assert reactions_for_messages(m.pk for m in messages) == expected
        assert messages[3].pk not in expected

    def test_no_op_writes_nothing(self, maya, arjun, room):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.reactions import set_reaction

        message = visible_text(room, arjun, "hi")
        with CaptureQueriesContext(connection) as ctx:
            _frame, changed = set_reaction(maya, room, str(message.id), "sad", False)
        assert changed is False
        assert not any(
            q["sql"].lstrip().upper().startswith(("INSERT", "DELETE", "SAVEPOINT"))
            for q in ctx.captured_queries
        )

    def test_history_and_page_carry_reactions(self, client, maya, arjun, room):
        message = visible_text(room, arjun, "hi")
        react(message, maya, "laugh")
        client.force_login(maya)
        response = client.get(reverse("chat:history", args=[room.id]))
        (data,) = response.json()["messages"]
        assert data["reactions"] == [
            {"emoji": "laugh", "count": 1, "users": [{"user": "maya", "name": "maya"}]}
        ]
        response = client.get(reverse("chat:chat"), {"room": room.id})
        assert response.context["room_messages"][0]["reactions"] == data["reactions"]
        assert len(response.context["reaction_emoji"]) == 6

    def test_history_costs_one_query_more_however_many_reactions(
        self, maya, arjun, room
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.models import Reaction
        from chat.views import history_page

        messages = make_messages(room, arjun, 30)

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                page, _ = history_page(room, maya)
            return page, [q["sql"] for q in ctx.captured_queries]

        page, bare = queries()
        assert all(m["reactions"] == [] for m in page)
        for m in messages:
            for emoji in ("thumbs_up", "heart", "laugh"):
                react(m, maya, emoji)
                react(m, arjun, emoji)
        page, busy = queries()
        assert len(busy) == len(bare)
        assert sum('"chat_reaction"' in q for q in busy) == 1
        assert all(m["reactions"][0]["count"] == 2 for m in page)
        assert Reaction.objects.count() == 180


@pytest.mark.django_db(transaction=True)
class TestReactionSockets:
    async def connect(self, room, *users):
        sockets = []
        for user in users:
            socket = make_communicator(room.id, user)
            assert (await socket.connect())[0]
            sockets.append(socket)
        return sockets

    async def close(self, *sockets):
        for socket in sockets:
            await socket.disconnect()

    async def reactions(self, message):
        from chat.models import Reaction

        def rows():
            return sorted(
                Reaction.objects.filter(message=message).values_list(
                    "user__username", "emoji"
                )
            )

        return await database_sync_to_async(rows)()

    async def test_on_and_off_reach_everyone_and_are_idempotent(
        self, maya, arjun, room
    ):
        message = await database_sync_to_async(visible_text)(room, arjun, "hi")
        maya_socket, arjun_socket = await self.connect(room, maya, arjun)
        frame = {"type": "react", "id": str(message.id), "emoji": "heart"}

        await maya_socket.send_json_to({**frame, "on": True})
        expected = {
            "type": "reactions_updated",
            "id": str(message.id),
            "reactions": [
                {
                    "emoji": "heart",
                    "count": 1,
                    "users": [{"user": "maya", "name": "maya"}],
                }
            ],
        }
        for socket in (maya_socket, arjun_socket):
            assert await socket.receive_json_from() == expected
        assert await self.reactions(message) == [("maya", "heart")]

        # Already on: success, nothing saved twice, only the sender hears.
        await maya_socket.send_json_to({**frame, "on": True})
        assert await maya_socket.receive_json_from() == expected
        assert await arjun_socket.receive_nothing(timeout=0.1)
        assert await self.reactions(message) == [("maya", "heart")]

        # Own messages too.
        await arjun_socket.send_json_to({**frame, "on": True})
        for socket in (maya_socket, arjun_socket):
            data = await socket.receive_json_from()
            assert data["reactions"][0]["count"] == 2

        await maya_socket.send_json_to({**frame, "on": False})
        for socket in (maya_socket, arjun_socket):
            data = await socket.receive_json_from()
            assert data["reactions"] == [
                {
                    "emoji": "heart",
                    "count": 1,
                    "users": [{"user": "arjun", "name": "arjun"}],
                }
            ]
        await maya_socket.send_json_to({**frame, "on": False})
        assert (await maya_socket.receive_json_from())["type"] == "reactions_updated"
        assert await arjun_socket.receive_nothing(timeout=0.1)
        assert await self.reactions(message) == [("arjun", "heart")]
        await self.close(maya_socket, arjun_socket)

    async def test_refused_targets_and_bad_frames_get_one_error(
        self, maya, arjun, lee, room
    ):
        from django.utils import timezone

        def build():
            other = Room.objects.create(name="other", type=Room.RoomTypes.PRIVATE)
            other.members.add(maya, lee)
            elsewhere = visible_text(other, lee, "elsewhere")
            system = Message.objects.create(
                content="event", room=room, user=arjun, kind=Message.Kinds.SYSTEM
            )
            system.visible_for.add(maya, arjun)
            deleted = visible_text(room, arjun, "gone")
            Message.objects.filter(pk=deleted.pk).update(
                content="", deleted_at=timezone.now()
            )
            hidden = visible_text(room, arjun, "cleared", visible=[arjun])
            fine = visible_text(room, arjun, "fine")
            return [elsewhere, system, deleted, hidden], fine

        refused, fine = await database_sync_to_async(build)()
        (socket,) = await self.connect(room, maya)
        good = {"type": "react", "id": str(fine.id), "emoji": "heart", "on": True}
        frames = [{**good, "id": str(m.id)} for m in refused] + [
            {**good, "id": "not-a-uuid"},
            {**good, "id": 7},
            {**good, "id": None},
            {k: v for k, v in good.items() if k != "id"},
            {**good, "id": "00000000-0000-0000-0000-000000000000"},
            {**good, "emoji": "skull"},
            {**good, "emoji": "👍"},
            {**good, "emoji": ["heart"]},
            {k: v for k, v in good.items() if k != "emoji"},
            {**good, "on": "true"},
            {**good, "on": 1},
            {**good, "on": None},
            {k: v for k, v in good.items() if k != "on"},
        ]
        for i, frame in enumerate(frames):
            await socket.send_json_to(frame)
            assert without_ts(await socket.receive_json_from()) == CANT_REACT_FRAME
            if i % 10 == 9:
                # Every react frame counts toward the rate limit: start a
                # fresh window.
                from django.core.cache import cache

                cache.clear()
        from chat.models import Reaction

        count = await database_sync_to_async(Reaction.objects.count)()
        assert count == 0
        await self.close(socket)

    async def test_rate_limit(self, maya, arjun, room):
        from chat.models import Reaction

        message = await database_sync_to_async(visible_text)(room, arjun, "hi")
        (socket,) = await self.connect(room, maya)
        for _ in range(10):
            await socket.send_json_to(
                {"type": "react", "id": str(message.id), "emoji": "nope", "on": True}
            )
            assert (await socket.receive_json_from())["code"] == 400
        await socket.send_json_to(
            {"type": "react", "id": str(message.id), "emoji": "heart", "on": True}
        )
        assert without_ts(await socket.receive_json_from()) == {
            "type": "error",
            "code": 429,
            "message": "Slow down",
            "for": "react",
        }
        assert not await database_sync_to_async(Reaction.objects.exists)()
        await self.close(socket)

    async def test_limit_is_shared_by_a_users_sockets_and_reconnects(
        self, maya, arjun, room
    ):
        from chat.models import Reaction

        message = await database_sync_to_async(visible_text)(room, arjun, "hi")
        bad = {"type": "react", "id": str(message.id), "emoji": "nope", "on": True}
        good = {**bad, "emoji": "heart"}
        first, second = await self.connect(room, maya, maya)
        for socket in [first] * 5 + [second] * 5:
            await socket.send_json_to(bad)
            assert (await socket.receive_json_from())["code"] == 400
        await second.send_json_to(good)
        assert (await second.receive_json_from())["code"] == 429
        await self.close(first, second)
        (again,) = await self.connect(room, maya)
        await again.send_json_to(good)
        assert (await again.receive_json_from())["code"] == 429
        # Other people have their own window.
        (other,) = await self.connect(room, arjun)
        await other.send_json_to(good)
        assert (await other.receive_json_from())["type"] == "reactions_updated"
        assert (
            await database_sync_to_async(Reaction.objects.filter(user=maya).exists)()
            is False
        )
        await self.close(again, other)

    async def test_busy_database_gets_503_and_keeps_socket(
        self, maya, arjun, room, monkeypatch
    ):
        from django.db import OperationalError

        from chat import reactions

        def locked(*args, **kwargs):
            raise OperationalError("database is locked")

        message = await database_sync_to_async(visible_text)(room, arjun, "hi")
        (socket,) = await self.connect(room, maya)
        monkeypatch.setattr(reactions, "set_reaction", locked)
        frame = {"type": "react", "id": str(message.id), "emoji": "heart", "on": True}
        await socket.send_json_to(frame)
        assert without_ts(await socket.receive_json_from()) == {
            "type": "error",
            "code": 503,
            "message": "Try again",
            "for": "react",
        }
        monkeypatch.undo()
        await socket.send_json_to(frame)
        assert (await socket.receive_json_from())["type"] == "reactions_updated"
        await self.close(socket)

    async def test_audience_is_people_who_still_see_it(self, maya, arjun, lee, group):
        from chat.models import Membership

        def build():
            message = visible_text(group, maya, "hi", visible=[maya, arjun, lee])
            arjun.visible_for.remove(message)  # arjun cleared history
            sam = User.objects.create_user("sam", password="pw")
            group.members.add(sam)  # joined later: can't see it
            return message, sam

        message, sam = await database_sync_to_async(build)()
        sockets = await self.connect(group, maya, arjun, lee, sam)
        # Lee is removed but their socket missed the revoke event.
        await database_sync_to_async(
            Membership.objects.filter(room=group, user=lee).delete
        )()
        await sockets[0].send_json_to(
            {"type": "react", "id": str(message.id), "emoji": "wow", "on": True}
        )
        assert (await sockets[0].receive_json_from())["type"] == "reactions_updated"
        for socket in sockets[1:]:
            assert await socket.receive_nothing(timeout=0.1)
        # Arjun can't react to what he cleared.
        await sockets[1].send_json_to(
            {"type": "react", "id": str(message.id), "emoji": "wow", "on": True}
        )
        assert without_ts(await sockets[1].receive_json_from()) == CANT_REACT_FRAME
        await self.close(*sockets)

    async def test_edit_carries_reactions_and_delete_clears_them(
        self, maya, arjun, room
    ):
        from chat.models import Reaction

        def build():
            message = visible_text(room, maya, "hi")
            react(message, arjun, "party")
            return message

        message = await database_sync_to_async(build)()
        maya_socket, arjun_socket = await self.connect(room, maya, arjun)
        await maya_socket.send_json_to(
            {"type": "edit_message", "id": str(message.id), "message": "hey"}
        )
        for socket in (maya_socket, arjun_socket):
            frame = await socket.receive_json_from()
            assert frame["type"] == "message_updated"
            assert frame["reactions"][0]["users"] == [
                {"user": "arjun", "name": "arjun"}
            ]
        await maya_socket.send_json_to(
            {"type": "delete_message", "id": str(message.id)}
        )
        for socket in (maya_socket, arjun_socket):
            frame = await socket.receive_json_from()
            assert (frame["deleted"], frame["reactions"]) == (True, [])
        assert not await database_sync_to_async(Reaction.objects.exists)()
        await self.close(maya_socket, arjun_socket)

    async def test_new_messages_and_inbox_carry_none(self, maya, arjun, room):
        message = await database_sync_to_async(visible_text)(room, arjun, "q")
        inbox = make_inbox(arjun)
        await inbox.connect()
        await inbox.receive_json_from()  # presence snapshot
        (socket,) = await self.connect(room, maya)
        await socket.send_json_to({"type": "save_message", "message": "a"})
        assert (await socket.receive_json_from())["reactions"] == []
        frame = await next_frame_of_type(inbox, "room_activity")
        assert frame["message"]["reactions"] == []
        # Reacting changes nothing in the room list.
        await socket.send_json_to(
            {"type": "react", "id": str(message.id), "emoji": "sad", "on": True}
        )
        assert (await socket.receive_json_from())["type"] == "reactions_updated"
        assert await inbox.receive_nothing(timeout=0.2)
        await self.close(socket, inbox)


class TestReactRateLimitWindow:
    def test_window_slides_per_user(self):
        from chat.reactions import rate_limited

        assert not any(rate_limited(1, now=100.0) for _ in range(10))
        assert rate_limited(1, now=100.0)
        assert not rate_limited(2, now=100.0)  # someone else
        assert rate_limited(1, now=104.9)
        # The first ten are now 5 s old.
        assert not rate_limited(1, now=105.0)


class TestRedisSettings:
    """With REDIS_URL set, the cache is Redis too, so per-user limits
    (reactions) are shared across processes."""

    def test_redis_url_sets_cache_and_channel_layer(self, monkeypatch):
        import importlib

        import realtime_chat.settings as base

        monkeypatch.setenv("DJANGO_DEBUG", "true")
        monkeypatch.setenv("REDIS_URL", "redis://redis.example:6379/0")
        try:
            importlib.reload(base)
            assert base.CACHES["default"]["BACKEND"].endswith("RedisCache")
            assert base.CACHES["default"]["LOCATION"] == "redis://redis.example:6379/0"
            assert base.CHANNEL_LAYERS["default"]["BACKEND"].startswith(
                "channels_redis"
            )
            monkeypatch.delenv("REDIS_URL")
            del base.CACHES  # reload keeps old module attributes
            importlib.reload(base)
            assert not hasattr(base, "CACHES")
        finally:
            monkeypatch.delenv("REDIS_URL", raising=False)
            importlib.reload(base)


# Mentions (P10c)


@pytest.fixture
def team(maya, arjun, lee):
    """A group with maya, arjun, lee and "Lee.Chen" (a createsuperuser-style
    username); first names so mentions carry names."""
    from chat.services import create_group_room

    User.objects.filter(pk=maya.pk).update(first_name="Maya", last_name="Rao")
    User.objects.filter(pk=arjun.pk).update(first_name="Arjun", last_name="Kumar")
    User.objects.create_user("Lee.Chen", password="pw")
    return create_group_room(maya, "Team", ["arjun", "lee", "Lee.Chen"])


def mentioned_usernames(message):
    from chat.models import Mention

    return sorted(
        Mention.objects.filter(message=message).values_list("user__username", flat=True)
    )


@pytest.mark.django_db
class TestFindMentions:
    @pytest.fixture
    def people(self, db):
        return {
            name: User.objects.create_user(name, password="pw")
            for name in ("maya", "lee", "lee.chen", "a+b", "ops-bot")
        }

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("@maya hi", ["maya"]),
            ("hi @maya", ["maya"]),
            ("@MAYA and @Lee", ["maya", "lee"]),
            ("@lee, @maya.", ["lee", "maya"]),
            ("(@lee) @maya! @maya?", ["lee", "maya"]),
            ("@lee: done; @maya", ["lee", "maya"]),
            ("@lee.", ["lee"]),
            ("@lee...", ["lee"]),
            ("mail a@maya.com", []),
            ("x@maya", []),
            ("9@maya _@maya", []),
            ("@mayabee", []),
            ("@may", []),
            ("@ maya", []),
            ("@lee.chen ships", ["lee.chen"]),
            ("@lee.chenx", []),
            ("@a+b and @ops-bot", ["a+b", "ops-bot"]),
            ("@maya@lee", []),
            ("@@maya", ["maya"]),
            ("@unknown", []),
            ("", []),
            ("@maya @maya @MAYA", ["maya"]),
            ("@lee then @maya then @lee", ["lee", "maya"]),
        ],
    )
    def test_table(self, people, text, expected):
        from chat.mentions import find_mentions

        found = find_mentions(text, people.values())
        assert [u.username for u in found] == expected

    def test_only_candidates_match(self, people):
        from chat.mentions import find_mentions

        assert find_mentions("@maya @lee", [people["lee"]]) == [people["lee"]]
        assert find_mentions("@maya", []) == []


def send_and_receive(room, user, payload):
    """Send one frame from `user` on a fresh room socket and return the first
    frame back (the sender's own copy)."""
    from asgiref.sync import async_to_sync

    async def run():
        socket = make_communicator(room.id, user)
        assert (await socket.connect())[0]
        await socket.send_json_to(payload)
        frame = await socket.receive_json_from(timeout=2)
        await socket.disconnect()
        return frame

    return async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
class TestMentionsOnSave:
    def test_save_stores_and_sends_mentions_in_order(self, team, maya):
        frame = send_and_receive(
            team, maya, {"type": "save_message", "message": "@lee then @Arjun"}
        )
        assert frame["type"] == "save_message"
        assert frame["mentions"] == [
            {"user": "lee", "name": "Lee"},
            {"user": "arjun", "name": "Arjun Kumar"},
        ]
        message = Message.objects.get(id=frame["id"])
        assert mentioned_usernames(message) == ["arjun", "lee"]
        assert list(message.mentions.order_by("username")) == list(
            User.objects.filter(username__in=["arjun", "lee"]).order_by("username")
        )

    def test_self_unknown_non_member_and_email_are_plain(self, team, maya):
        User.objects.create_user("eve", password="pw")
        frame = send_and_receive(
            team,
            maya,
            {"type": "save_message", "message": "@maya @eve @nobody lee@arjun.com"},
        )
        assert frame["mentions"] == []
        assert mentioned_usernames(Message.objects.get(id=frame["id"])) == []

    def test_removed_member_is_not_mentioned(self, team, maya, lee):
        from chat import groups

        groups.remove_member(team, maya, lee)
        frame = send_and_receive(
            team, maya, {"type": "save_message", "message": "@lee are you there?"}
        )
        assert frame["mentions"] == []

    def test_superuser_style_username(self, team, maya):
        frame = send_and_receive(
            team, maya, {"type": "save_message", "message": "ping @lee.chen."}
        )
        assert [m["user"] for m in frame["mentions"]] == ["Lee.Chen"]

    def test_direct_chat_mentions_are_stored(self, room, maya):
        frame = send_and_receive(
            room, maya, {"type": "save_message", "message": "@arjun look"}
        )
        assert [m["user"] for m in frame["mentions"]] == ["arjun"]


@pytest.mark.django_db(transaction=True)
class TestMentionsOnEditDelete:
    def test_edit_adds_and_removes(self, team, maya):
        message = visible_text(team, maya, "@lee hi")
        from chat.mentions import find_mentions, sync_mentions

        sync_mentions(message, find_mentions(message.content, team.members.all()))
        assert mentioned_usernames(message) == ["lee"]
        frame = send_and_receive(
            team,
            maya,
            {"type": "edit_message", "id": str(message.id), "message": "@arjun hi"},
        )
        assert frame["type"] == "message_updated"
        assert [m["user"] for m in frame["mentions"]] == ["arjun"]
        assert mentioned_usernames(message) == ["arjun"]

    def test_edit_only_mentions_people_who_can_see_it(self, team, maya, arjun, lee):
        # lee cleared it (or joined later): he can't be mentioned by an edit.
        message = visible_text(team, maya, "hi", visible=[maya, arjun])
        frame = send_and_receive(
            team,
            maya,
            {"type": "edit_message", "id": str(message.id), "message": "@lee @arjun"},
        )
        assert [m["user"] for m in frame["mentions"]] == ["arjun"]

    def test_unchanged_edit_keeps_mentions(self, team, maya):
        from chat.mentions import find_mentions, sync_mentions

        message = visible_text(team, maya, "@lee hi")
        sync_mentions(message, find_mentions(message.content, team.members.all()))
        frame = send_and_receive(
            team,
            maya,
            {"type": "edit_message", "id": str(message.id), "message": "@lee hi"},
        )
        assert [m["user"] for m in frame["mentions"]] == ["lee"]

    def test_delete_removes_mentions(self, team, maya):
        from chat.mentions import find_mentions, sync_mentions

        message = visible_text(team, maya, "@lee @arjun")
        sync_mentions(message, find_mentions(message.content, team.members.all()))
        frame = send_and_receive(
            team, maya, {"type": "delete_message", "id": str(message.id)}
        )
        assert frame["deleted"] is True
        assert frame["mentions"] == []
        assert mentioned_usernames(message) == []

    def test_deleting_the_message_row_cascades(self, team, maya):
        from chat.mentions import find_mentions, sync_mentions
        from chat.models import Mention

        message = visible_text(team, maya, "@lee")
        sync_mentions(message, find_mentions(message.content, team.members.all()))
        message.delete()
        assert not Mention.objects.exists()


def mention(message, *users):
    from chat.models import Mention

    for user in users:
        Mention.objects.create(message=message, user=user)
    return message


@pytest.mark.django_db
class TestMentionsInHistory:
    def test_history_and_page_carry_mentions(self, client, team, maya, arjun, lee):
        message = mention(visible_text(team, arjun, "@lee and @maya"), maya, lee)
        system = Message.objects.create(
            content="@lee joined", room=team, user=maya, kind=Message.Kinds.SYSTEM
        )
        system.visible_for.add(maya)
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": team.id})
        rows = {m["id"]: m for m in response.context["room_messages"]}
        # In order of appearance, not of the rows.
        assert rows[str(message.id)]["mentions"] == [
            {"user": "lee", "name": "Lee"},
            {"user": "maya", "name": "Maya Rao"},
        ]
        assert rows[str(system.id)]["mentions"] == []
        data = client.get(reverse("chat:history", args=[team.id])).json()
        found = next(m for m in data["messages"] if m["id"] == str(message.id))
        assert [m["user"] for m in found["mentions"]] == ["lee", "maya"]

    def test_deleted_message_has_no_mentions(self, team, maya, lee):
        from django.utils import timezone

        from chat.views import history_page

        message = mention(visible_text(team, maya, "@lee"), lee)
        Message.objects.filter(pk=message.pk).update(deleted_at=timezone.now())
        page, _ = history_page(team, maya)
        assert page[-1]["mentions"] == []

    def test_history_adds_one_flat_query(self, team, maya, arjun, lee):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.views import history_page

        counts = []
        for total in (1, 30):
            while Message.objects.filter(room=team).count() < total:
                mention(visible_text(team, arjun, "@lee @maya"), lee, maya)
            with CaptureQueriesContext(connection) as ctx:
                history_page(team, maya)
            counts.append(len(ctx.captured_queries))
            assert any("chat_mention" in q["sql"] for q in ctx.captured_queries)
        assert counts[0] == counts[1] == 3

    def test_page_has_room_members_sorted_by_name(self, client, team, maya):
        client.force_login(maya)
        response = client.get(reverse("chat:chat"), {"room": team.id})
        members = response.context["room_members"]
        assert [m["username"] for m in members] == ["arjun", "lee", "Lee.Chen", "maya"]
        assert members[0] == {
            "username": "arjun",
            "name": "Arjun Kumar",
            "initials": "AK",
        }
        assert client.get(reverse("chat:chat")).context["room_members"] == []


@pytest.mark.django_db
class TestMentionCounts:
    def summaries(self, user):
        from chat.presenters import room_summaries

        return {r["id"]: r for r in room_summaries(user)}

    def test_mentions_and_replies_to_you_count(self, team, maya, arjun, lee):
        own = visible_text(team, maya, "question")
        mention(visible_text(team, arjun, "@maya look"), maya)
        reply(team, lee, own, "answer")
        visible_text(team, arjun, "plain")
        mention(visible_text(team, arjun, "@lee"), lee)
        row = self.summaries(maya)[str(team.id)]
        assert (row["unread"], row["mentions"]) == (4, 2)
        assert self.summaries(lee)[str(team.id)]["mentions"] == 1

    def test_a_reply_that_mentions_you_counts_once(self, team, maya, arjun):
        own = visible_text(team, maya, "q")
        mention(reply(team, arjun, own, "@maya a"), maya)
        assert self.summaries(maya)[str(team.id)]["mentions"] == 1

    def test_own_messages_and_hidden_ones_dont_count(self, team, maya, arjun):
        own = visible_text(team, maya, "q")
        reply(team, maya, own, "self reply")
        mention(visible_text(team, arjun, "@maya", visible=[arjun]), maya)
        assert self.summaries(maya)[str(team.id)]["mentions"] == 0

    def test_direct_chats_are_always_zero(self, room, maya, arjun):
        own = visible_text(room, maya, "q")
        reply(room, arjun, own, "a")
        mention(visible_text(room, arjun, "@maya"), maya)
        row = self.summaries(maya)[str(room.id)]
        assert (row["unread"], row["mentions"]) == (2, 0)

    def test_cleared_on_read(self, team, maya, arjun):
        from chat import presence

        mention(visible_text(team, arjun, "@maya"), maya)
        presence.mark_read(maya, team)
        assert self.summaries(maya)[str(team.id)]["mentions"] == 0

    def test_summaries_endpoint(self, client, team, maya, arjun):
        mention(visible_text(team, arjun, "@maya"), maya)
        client.force_login(maya)
        rooms = client.get(reverse("chat:summaries")).json()["rooms"]
        assert rooms[0]["mentions"] == 1
        one = client.get(reverse("chat:summary", args=[team.id])).json()
        assert one["mentions"] == 1

    def test_room_summaries_for_users_matches(self, team, maya, arjun, lee):
        from chat.presenters import room_summaries_for_users, room_summary

        own = visible_text(team, maya, "q")
        reply(team, lee, own, "a")
        mention(visible_text(team, arjun, "@maya @lee"), maya, lee)
        users = list(team.members.all())
        many = room_summaries_for_users(team.id, users)
        for user in users:
            assert many[user.pk] == room_summary(user, team.id)
        assert many[maya.pk]["mentions"] == 2
        assert many[lee.pk]["mentions"] == 1
        assert many[arjun.pk]["mentions"] == 0

    def test_room_summaries_for_users_direct_is_zero(self, room, maya, arjun):
        from chat.presenters import room_summaries_for_users

        mention(visible_text(room, arjun, "@maya"), maya)
        assert room_summaries_for_users(room.id, [maya])[maya.pk]["mentions"] == 0

    def test_no_extra_query(self, team, maya, arjun):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.presence import unread_and_mentions

        counts = []
        for total in (1, 20):
            while Message.objects.filter(room=team).count() < total:
                mention(visible_text(team, arjun, "@maya"), maya)
            with CaptureQueriesContext(connection) as ctx:
                result = unread_and_mentions(maya, [team.pk])
            counts.append(len(ctx.captured_queries))
            assert result[team.pk] == (total, total)
        # One for read states, one grouped count, as before mentions.
        assert counts == [2, 2]

    def test_rooms_for_queries_stay_flat(self, maya, arjun):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.presenters import rooms_for

        counts = []
        for total in (2, 8):
            while maya.rooms.count() < total:
                r = Room.objects.create(name="g", type=Room.RoomTypes.GROUP)
                r.members.add(maya, arjun)
                mention(visible_text(r, arjun, "@maya"), maya)
            with CaptureQueriesContext(connection) as ctx:
                rows = rooms_for(maya)
            counts.append(len(ctx.captured_queries))
            assert all(r["mentions"] == 1 for r in rows)
        assert counts[0] == counts[1]

    def test_room_summaries_for_users_queries_stay_flat(self, maya):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.presenters import room_summaries_for_users
        from chat.services import MAX_GROUP_MEMBERS

        people = make_users("p", MAX_GROUP_MEMBERS - 1)
        group = Room.objects.create(name="big", type=Room.RoomTypes.GROUP)
        group.members.add(maya, *people)
        counts = []
        for size in (2, MAX_GROUP_MEMBERS):
            viewers = [maya, *people][:size]
            mention(visible_text(group, people[0], "@x"), *viewers[1:2])
            with CaptureQueriesContext(connection) as ctx:
                room_summaries_for_users(group.id, viewers)
            counts.append(len(ctx.captured_queries))
        assert counts[0] == counts[1]


@pytest.mark.django_db(transaction=True)
class TestMentionInboxFrames:
    async def activity_for(self, room, sender, payload, *recipients):
        inboxes = []
        for user in recipients:
            inbox = make_inbox(user)
            await inbox.connect()
            await inbox.receive_json_from()  # snapshot
            inboxes.append(inbox)
        socket = make_communicator(room.id, sender)
        await socket.connect()
        await socket.send_json_to(payload)
        frames = [await next_frame_of_type(i, "room_activity") for i in inboxes]
        await socket.disconnect()
        for inbox in inboxes:
            await inbox.disconnect()
        return frames

    async def test_mention_reply_and_plain_per_recipient(self, team, maya, arjun, lee):
        own = await database_sync_to_async(visible_text)(team, arjun, "question")
        to_maya, to_arjun, to_lee = await self.activity_for(
            team,
            lee,
            {"type": "save_message", "message": "@maya see", "reply_to": str(own.id)},
            maya,
            arjun,
            lee,
        )
        assert (to_maya["for_you"], to_maya["mentions"], to_maya["unread"]) == (
            "mention",
            1,
            2,
        )
        assert (to_arjun["for_you"], to_arjun["mentions"]) == ("reply", 1)
        # The sender: never for them, and sending marks the room read.
        assert (to_lee["for_you"], to_lee["mentions"], to_lee["unread"]) == (
            None,
            0,
            0,
        )
        assert to_maya["message"]["mentions"] == [{"user": "maya", "name": "Maya Rao"}]
        assert to_maya["message"]["reply_to"] is None

    async def test_direct_chat_is_never_for_you(self, room, maya, arjun):
        own = await database_sync_to_async(visible_text)(room, arjun, "q")
        (frame,) = await self.activity_for(
            room,
            maya,
            {"type": "save_message", "message": "@arjun a", "reply_to": str(own.id)},
            arjun,
        )
        assert (frame["for_you"], frame["mentions"]) == (None, 0)

    def test_inbox_message_is_one_query_without_loading_the_room(
        self, team, maya, arjun
    ):
        from unittest import mock

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from chat.channels.consumers import InboxConsumer

        mention(visible_text(team, arjun, "@maya"), maya)
        consumer = InboxConsumer()
        consumer.user = maya
        sent = []
        event = {
            "type": "inbox.message",
            "room": str(team.id),
            "group": True,
            "author": arjun.pk,
            "mentioned": [maya.pk],
            "reply_to_author": None,
            "data": {"id": "x"},
        }
        with mock.patch.object(
            consumer, "send", side_effect=lambda text_data: sent.append(text_data)
        ):
            with CaptureQueriesContext(connection) as ctx:
                consumer.inbox_message(event)
        assert len(ctx.captured_queries) == 1
        # The room itself is never read (only its messages and read state).
        assert '"chat_room"' not in ctx.captured_queries[0]["sql"]
        frame = json.loads(sent[0])
        assert (frame["unread"], frame["mentions"], frame["for_you"]) == (
            1,
            1,
            "mention",
        )
