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
at the same "@" ("lee" and "lee.chen"), the longer one wins. Case is
compared with casefold() on both sides. Only the first MAX_MENTION_SIGNS
eligible "@" signs of a message are looked at.

Mention rows record what a message's text says, whoever can see it now: they
aren't removed or skipped when someone clears their history, because the
author would then see the highlight change and learn who cleared. Anything
that tells a user something is "for them" (counts, frames, notifications)
must also require the message to be in their visible_for.
"""

from chat.models import Mention

# Characters that may appear in a username besides letters and digits
# (Django's default validator allows these).
_USERNAME_PUNCTUATION = frozenset("@.+-_")

# At most this many "@" signs are looked at per message, so a message made
# of "@" signs costs no more than a normal one. 4000 characters fit at most
# 2000 possible mentions; nobody names 200 people in one message.
MAX_MENTION_SIGNS = 200


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


def _fold(text):
    return text.casefold()


def mention_positions(content, candidates):
    """[(position, user)] for the candidates named in `content`, each once
    at its first mention, in order. Positions are offsets in the case-folded
    text (only useful for ordering)."""
    if not content or "@" not in content:
        return []
    # {length: {folded username: user}}, longest first, so "lee.chen" wins
    # over "lee" at the same "@". One dict lookup per distinct length.
    by_length = {}
    for user in candidates:
        name = _fold(user.username or "")
        if name:
            by_length.setdefault(len(name), {})[name] = user
    if not by_length:
        return []
    lengths = sorted(by_length, reverse=True)
    # Matching works on the folded text throughout, so "İlker" and "STRASSE"
    # compare correctly even where folding changes the length.
    text = _fold(content)
    found = []
    seen = set()
    signs = 0
    position = text.find("@")
    while position != -1 and signs < MAX_MENTION_SIGNS:
        next_from = position + 1
        if position == 0 or not _word_char(text[position - 1]):
            signs += 1
            start = position + 1
            for length in lengths:
                end = start + length
                user = by_length[length].get(text[start:end])
                if user is not None and _ends_handle(text, end):
                    if user.pk not in seen:
                        seen.add(user.pk)
                        found.append((position, user))
                    next_from = end
                    break
        position = text.find("@", next_from)
    return found


def find_mentions(content, candidates):
    """The users in `candidates` named in `content`, each once, in order of
    their first mention."""
    return [user for _position, user in mention_positions(content, candidates)]


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
