from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render


def csrf_failure(request, reason=""):
    """Render CSRF failures with the site's error page instead of Django's."""
    return render(request, "403_csrf.html", {"title": "Form expired"}, status=403)


def home(request):
    """Public landing page; signed-in users go straight to their chats."""
    if request.user.is_authenticated:
        return redirect("chat:chat")
    return render(
        request, "core/home.html", {"title": "Every conversation, on one line"}
    )


def styleguide(request):
    """Component gallery for development; not available when DEBUG is off."""
    if not settings.DEBUG:
        raise Http404
    sample_messages = [
        {"day": "Yesterday"},
        {
            "time": "18:02",
            "initials": "MR",
            "name": "Maya",
            "text": "Shipping the compact layout tonight",
        },
        {
            "time": "18:02",
            "text": "Rows are one line unless the text wraps",
            "cont": True,
        },
        {"day": "Today"},
        {
            "time": "09:38",
            "initials": "AK",
            "name": "Arjun",
            "text": "Morning. Pulled the branch",
        },
        {
            "time": "09:41",
            "initials": "YO",
            "name": "You",
            "text": "Consecutive messages skip the name",
            "mine": True,
        },
        {
            "time": "09:41",
            "text": "Times show on hover for those",
            "mine": True,
            "cont": True,
        },
    ]
    return render(
        request,
        "core/styleguide.html",
        {"title": "Style guide", "sample_messages": sample_messages},
    )
