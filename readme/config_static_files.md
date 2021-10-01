# Static Files

Any additional files like images, CSS, JavaScripts which are needed to be served are refered to as static files.  

## Basic Configuration

Store the static files in a directory called `static` in application directory.  

Load template tag `static` in the html file where the static files are to be loaded. Make sure that the template tag `extends` is at the top of the structure.

```html
{% extends "chats/base.html" %}
{% load static %}
```

Use `static` template tag to load static file

```html
<link rel="stylesheet" href="{% static 'chats/box.css' %}">
```

Additionally if there are any static files that aren’t tied to a particular app, they can stored in other directory/ies and those paths can be defined as a list of directories using `STATICFILES_DIRS` in [settings.py].

```python
STATICFILES_DIRS = [
    BASE_DIR / "assets",
    '/var/www/assets/',
]
```

## Namespacing

Django will use the first static file it finds whose name matches, and if there's a static file with the same name in a different application, Django would be unable to distinguish between them. So, it is best to ensure this by namespacing them. That is, by putting those static files inside another directory named for the application itself eg: `chats/static/chats/box.js`.

## Serving files during development

As long as `DEBUG = True` and `django.contrib.staticfiles` is in `INSTALLED_APPS` in [settings.py] the static files with be served automatically by the `runserver` command.  

**This method is inefficient and probably insecure to use in production.**

<!-- File links -->
[settings.py]: ./realtime_chat/settings.py
