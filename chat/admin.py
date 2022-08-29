from django.contrib import admin

from chat.models import Message, Room


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("id", "room", "user", "created_at")
    list_filter = ("user", "room")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    search_fields = ("id", "room__name", "user__username")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("id", "name", "type", "members_count", "created_at")
    list_filter = ("type",)
    ordering = ("created_at",)
    search_fields = ("id", "name")

    @admin.display(description="Count members")
    def members_count(self, obj):
        return obj.members.count()
