"""Demo dataset for local development. Loaded by `manage.py seed_demo`.

Everything here is fictional. Keep docs/demo-data.md in sync when changing
users, rooms or scenarios.
"""

# Every demo account signs in with this password. Debug mode only.
DEMO_PASSWORD = "relay-demo-123"

# username, first name, last name, active, (palette, mode, density) or None
USERS = [
    ("maya", "Maya", "Rao", True, None),
    ("arjun", "Arjun", "Kumar", True, ("slate", "dark", "compact")),
    ("anika", "Anika", "Shah", True, ("plum", "light", "comfortable")),
    ("lee", "Lee", "Chen", True, ("midnight", "system", "compact")),
    ("sofia", "Sofia", "Martins", True, ("moss", "dark", "comfortable")),
    ("omar", "Omar", "Haddad", True, ("paper", "light", "compact")),
    ("priya", "Priya", "Nair", True, None),
    ("sam", "Sam", "Taylor", True, None),
    ("noah", "Noah", "Kim", False, None),
]

# Rooms: key, name, type, members. For groups the first member is the
# creator (and first admin); members join in the order listed.
ROOMS = [
    ("design", "Design team", "group", ["maya", "arjun", "anika", "lee"]),
    ("ops", "Ops", "group", ["lee", "omar", "sofia", "maya"]),
    ("books", "Book club", "group", ["anika", "sofia", "priya", "omar", "maya"]),
    ("maya-arjun", None, "private", ["maya", "arjun"]),
    ("maya-anika", None, "private", ["maya", "anika"]),
    ("arjun-lee", None, "private", ["arjun", "lee"]),
    ("sofia-priya", None, "private", ["sofia", "priya"]),
]

# Short scripted conversations: (room, sender, text, minutes before now),
# optionally followed by the exact text of an earlier line in the same room
# that this one replies to. "@username" names a member, as when typed in the
# app (see chat/mentions.py).
SCRIPT = [
    # Design team, three days ago to now
    ("design", "arjun", "Morning all. Kicking off the chat redesign this week.", 4320),
    (
        "design",
        "anika",
        "Finally! The old screen has been bugging me for months.",
        4315,
    ),
    ("design", "maya", "Let's agree on a direction by Wednesday.", 4310),
    ("design", "lee", "I'll pull together a few moodboards.", 4300),
    ("design", "lee", "@arjun the moodboards are in the shared folder", 4290),
    ("design", "arjun", "Pushed the new spine layout to staging", 2900),
    ("design", "arjun", "Rows are one line now unless the text wraps", 2899),
    ("design", "maya", "Looks great. The day markers really help.", 2890),
    ("design", "anika", "Morning! Reviewing the settings screen today", 95),
    ("design", "anika", "Palette cards are in, six of them", 94),
    ("design", "lee", "Can we keep Graphite + Coral as the default?", 80),
    (
        "design",
        "maya",
        "Yes, default stays. Everyone can switch in Settings → Appearance",
        78,
        "Can we keep Graphite + Coral as the default?",
    ),
    ("design", "arjun", "@maya @anika can you both review the spacing tokens?", 55),
    ("design", "arjun", "Typing indicator and unread badges are live too", 40),
    (
        "design",
        "arjun",
        "Try opening Ops in another tab",
        39,
        "Pushed the new spine layout to staging",
    ),
    (
        "design",
        "maya",
        "Edit and delete work on your own messages. Press ↑ to fix the last one",
        12,
    ),
    # A reply to Maya after she last read the room: "@" on her Design row.
    (
        "design",
        "lee",
        "Handy, I use ↑ all the time now",
        10,
        "Edit and delete work on your own messages. Press ↑ to fix the last one",
    ),
    ("design", "anika", "Shipping it after lunch 🚀", 3),
    # Ops
    ("ops", "omar", "Deploy window is 14:00 today.", 300),
    ("ops", "omar", "@lee can you watch the error rates after the deploy?", 290),
    ("ops", "sofia", "Database backups verified this morning.", 240),
    # Replies to a line deleted below, so its quote reads "Message deleted".
    (
        "ops",
        "lee",
        "Rolling out relay v1.0 now",
        30,
        "Database backups verified this morning.",
    ),
    ("ops", "sofia", "@maya the status page copy is ready for review", 20),
    ("ops", "omar", "Deploy finished: relay v1.0 is live", 8),
    ("ops", "lee", "Smoke tests passed", 6, "Deploy finished: relay v1.0 is live"),
    # Book club
    ("books", "anika", "Next pick: The Left Hand of Darkness?", 10080),
    ("books", "sofia", "Yes please, I've been meaning to read it.", 10070),
    ("books", "priya", "I'm in. Meeting on the 30th?", 10000),
    ("books", "omar", "Works for me.", 9990),
    # Before Priya's clear point: she never sees this mention.
    ("books", "anika", "@priya the 30th works, I'll book a table", 9985),
    # Priya cleared the older history, so she can't see what Maya quotes.
    (
        "books",
        "maya",
        "Halfway through, no spoilers please!",
        1440,
        "Next pick: The Left Hand of Darkness?",
    ),
    ("books", "priya", "Chapter 7 is so good", 200),
    # After it: Priya sees this one ("@" on her Book club row).
    ("books", "sofia", "@Priya same, it made me cry", 190),
    # Direct chats
    ("maya-arjun", "arjun", "Got a minute to look at the PR?", 30),
    (
        "maya-arjun",
        "maya",
        "Sure, sending notes in a bit",
        28,
        "Got a minute to look at the PR?",
    ),
    ("maya-anika", "anika", "Lunch at 1?", 50),
    ("arjun-lee", "lee", "Can you review the presence changes?", 120),
    ("arjun-lee", "arjun", "On it. Looks solid so far.", 110),
    ("sofia-priya", "priya", "Did you finish the book?", 400),
    ("sofia-priya", "sofia", "Two chapters left!", 390),
]

# Filler for the long Design team history, so infinite scroll has pages to
# load. Spread over the week before the scripted messages.
FILLER_ROOM = "design"
FILLER_SENDERS = ["maya", "arjun", "anika", "lee"]
FILLER_COUNT = 120
FILLER_LINES = [
    "Updated the Figma file with the new spacing.",
    "Can someone double-check the dark mode contrast?",
    "Merged. Thanks for the review!",
    "I think the composer needs more padding on phones.",
    "Standup in five.",
    "Pushed a fix for the overflow on long names.",
    "Nice, that reads much better.",
    "Let's revisit this after the demo.",
    "Added tests for the new endpoint.",
    "The rail view works well on the tablet.",
    "Who's taking notes today?",
    "Moving the meeting to Thursday.",
]

# Extra group admins besides each creator.
ADMINS = {"design": ["arjun"]}

# Group events shown as system messages: (room, actor, text, minutes before now).
SYSTEM = [
    ("design", "maya", "Maya Rao added Lee Chen", 4330),
    ("design", "maya", "Maya Rao made Arjun Kumar an admin", 4325),
    ("ops", "lee", "Lee Chen added Maya Rao", 320),
]

# Message edits and deletes, matched by room and exact text.
EDITED = [("design", "Shipping it after lunch 🚀", "Shipping it after lunch 🚀 (2pm)")]
DELETED = [("ops", "Database backups verified this morning.")]

# Reactions: (room, exact text of a text message, emoji key, [usernames]),
# the people in the order they reacted. Emoji keys are chat.models.ReactionEmoji
# values. Matched after edits, so use a message's final text.
REACTIONS = [
    # Several people, several emoji.
    ("design", "Palette cards are in, six of them", "thumbs_up", ["maya", "lee"]),
    ("design", "Palette cards are in, six of them", "party", ["arjun", "maya", "lee"]),
    ("design", "Palette cards are in, six of them", "heart", ["anika"]),  # her own
    ("design", "Typing indicator and unread badges are live too", "wow", ["lee"]),
    # A direct chat.
    ("maya-arjun", "Sure, sending notes in a bit", "heart", ["arjun"]),
    # Priya cleared this part of the history, so she never sees these.
    ("books", "Next pick: The Left Hand of Darkness?", "heart", ["sofia", "omar"]),
    ("books", "Next pick: The Left Hand of Darkness?", "laugh", ["maya"]),
]

# Read state: username -> {room: minutes before now when last read}.
# Rooms not listed have never been opened, so all messages from others count
# as unread.
READ = {
    "maya": {"design": 60, "maya-arjun": 0, "maya-anika": 60, "books": 0},
    "arjun": {"design": 0, "maya-arjun": 0, "arjun-lee": 0},
    "anika": {"design": 0, "books": 0, "maya-anika": 0},
    "lee": {"design": 0, "ops": 0},
}

# Clear history: (username, room) hides messages older than the given minutes.
CLEARED = [("priya", "books", 5000)]
