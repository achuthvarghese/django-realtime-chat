# Channels Basic Setup

Install [channels]

```sh
pip install -U channels
```

Add channels to `INSTALLED_APPS` in [settings.py]

```python
INSTALLED_APPS = [
    ...
    "channels",
]
```

Update project’s [asgi.py] to wrap the Django ASGI application:

```python
import os

from channels.routing import ProtocolTypeRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "realtime_chat.settings")

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        # Add other protocols later
    }
)
```

Add the asgi application using `ASGI_APPLICATION` in [settings.py].

```python
ASGI_APPLICATION = "realtime_chat.asgi.application"
```

Once development server is run using the `runserver` command, the server would use the ASGI application object specified in `ASGI_APPLICATION` instead of the default WSGI application.
![image01]

<!-- External Links -->
[channels]: https://pypi.org/project/channels/

<!-- File links -->
[settings.py]: ../realtime_chat/settings.py
[asgi.py]: ../realtime_chat/asgi.py

<!-- Image links -->
[image01]: ../screenshots/image01.PNG (Running local dev server using ASGI application)
