"""@username mentions: finding them in message text and keeping the Mention
rows in step with it.

A mention is "@" followed by a candidate's exact username, case-insensitive,
where the "@" doesn't directly follow a letter, digit or underscore (so
"a@maya.com" names nobody) and the username isn't the start of a longer word
or handle ("@leech" and "@lee.chen" don't name "lee"; "@lee," and "@lee."
do). Candidates are passed in by the caller: current members other than the
sender who can see the message. Anything else stays plain text and nobody
is told.

Usernames are matched directly rather than with a username pattern, because
accounts made with createsuperuser may contain characters ("@", "+", ".")
that the sign-up form doesn't allow. Where two candidates' usernames both fit
at the same "@" ("lee" and "lee.chen"), the longer one wins.
"""

from chat.models import Mention

# Characters that may appear in a username besides letters and digits
# (Django's default validator allows these).
_USERNAME_PUNCTUATION = set("@.+-_")


def _word_char(char):
    return char.isalnum() or char == "_"


def _ends_handle(text, end):
    """True if a username ending at `end` isn't followed by more of a
    username: the text ends, or the next character is neither a word
    character nor punctuation that leads into one (".chen", "-ops")."""
    if end >= len(text):
        return True
    char = text[end]
    if _word_char(char):
        return False
    if char in _USERNAME_PUNCTUATION:
        following = text[end + 1 : end + 2]
        return not (following and (_word_char(following) or following == "@"))
    return True


def find_mentions(content, candidates):
    """The users in `candidates` named in `content`, each once, in order of
    their first mention."""
    if not content or "@" not in content:
        return []
    # Longest first, so "lee.chen" wins over "lee" at the same "@".
    by_name = sorted(
        ((user.username.lower(), user) for user in candidates if user.username),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    if not by_name:
        return []
    found = []
    seen = set()
    position = content.find("@")
    while position != -1:
        if position == 0 or not _word_char(content[position - 1]):
            start = position + 1
            for name, user in by_name:
                end = start + len(name)
                if content[start:end].lower() == name and _ends_handle(content, end):
                    if user.pk not in seen:
                        seen.add(user.pk)
                        found.append(user)
                    position = end - 1
                    break
        position = content.find("@", position + 1)
    return found


def sync_mentions(message, users, new=False):
    """Make `message`'s Mention rows match `users` (from find_mentions):
    add the new ones, remove the rest. `new` says the message was just
    created, so it has none yet. Call inside the transaction that saves the
    message. Returns `users`."""
    wanted = {user.pk for user in users}
    if new:
        current = set()
    else:
        current = set(
            Mention.objects.filter(message=message).values_list("user_id", flat=True)
        )
    removed = current - wanted
    if removed:
        Mention.objects.filter(message=message, user_id__in=removed).delete()
    added = [Mention(message=message, user=u) for u in users if u.pk not in current]
    if added:
        Mention.objects.bulk_create(added, ignore_conflicts=True)
    return users


def clear_mentions(message):
    """Remove every mention of a message (it was deleted)."""
    Mention.objects.filter(message=message).delete()
