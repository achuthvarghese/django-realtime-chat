from django.contrib import admin
from django.contrib.admin import ModelAdmin

from chats.models import Message, Room


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ("id", "user", "room", "created_at")
    list_display_links = ("id", "user", "room")
    list_filter = ("user", "room")
    date_hierarchy = "created_at"


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    list_display = ("id", "type", "members_count", "created_at")
    list_filter = ("type",)
    search_fields = ("id",)
    date_hierarchy = "created_at"

    @admin.display(description="Count members")
    def members_count(self, obj):
        return obj.members.count()
