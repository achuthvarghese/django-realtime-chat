# Channels Basic Setup

Install [channels]

```sh
pip install -U "channels>=4.2" "daphne>=4.1"
```

Channels 4 no longer ships an ASGI server. Add `daphne` as the **first** entry
in `INSTALLED_APPS` so `runserver` starts the Daphne ASGI server, then add
`channels`:

```python
INSTALLED_APPS = [
    "daphne",
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

The project's [asgi.py] also routes `websocket` connections through
`AllowedHostsOriginValidator` and `AuthMiddlewareStack`; see the file for the
full version.

Once development server is run using the `runserver` command, the server would use the ASGI application object specified in `ASGI_APPLICATION` instead of the default WSGI application.
![image01]

<!-- External Links -->
[channels]: https://pypi.org/project/channels/

<!-- File links -->
[settings.py]: ../realtime_chat/settings.py
[asgi.py]: ../realtime_chat/asgi.py

<!-- Image links -->
[image01]: ../screenshots/image01.PNG (Running local dev server using ASGI application)
