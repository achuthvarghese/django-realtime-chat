from django.contrib import admin

from account.models import Preference


@admin.register(Preference)
class PreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "palette", "mode", "density", "updated_at")
    list_filter = ("palette", "mode", "density")
    search_fields = ("user__username",)
