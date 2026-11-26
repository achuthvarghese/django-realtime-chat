"""Rename existing accounts to the username rules in account/usernames.py.

Valid usernames are left alone. Others become their closest valid form
("Lee.Chen" -> "lee_chen"); clashes get _2, _3 and so on. Each rename is
printed so you can tell the people affected. Not reversible: the old names
are only kept in the migration output.
"""

from django.db import migrations


def conform_usernames(apps, schema_editor):
    from account.usernames import conform, is_valid, unique_variant

    User = apps.get_model("auth", "User")
    users = list(User.objects.order_by("pk"))
    # Valid names keep priority, so they never get a suffix.
    taken = {u.username for u in users if is_valid(u.username)}
    renames = []
    for user in users:
        if is_valid(user.username):
            continue
        new = unique_variant(conform(user.username), taken)
        taken.add(new)
        renames.append((user.username, new))
        user.username = new
        user.save(update_fields=["username"])
    if renames:
        print("\n  Renamed accounts to the new username rules:")
        for old, new in renames:
            print(f"    {old!r} -> {new!r}")


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0001_preference"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(conform_usernames, migrations.RunPython.noop),
    ]
