# Channel Layers Setup

Channel Layers have async interface and allows to talk between different instances of the application.  
Use either of Redis Channel Layers or In-Memory Channel Layers.

## Redis Channel Layer

Install [channels-redis]

```sh
pip install channels-redis
```

**Redis server should be running** while using this configuration else Websocket will be disconnected after handshake.  
Use [docker-compose.yml] to run Redis server (Requires [Docker]).  

```sh
docker-compose -f "docker-compose.yml" up
```

This will run the Redis server on localhost (127.0.0.1) port 6379.

Configure Redis Channel Layers using `CHANNEL_LAYERS` in [settings.py].

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}
```

## In-Memory Channel Layer

This layer can be used for Testing or local-development purposes.  
Configure In-Memory Channel Layers using `CHANNEL_LAYERS` in [settings.py].

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}
```

**Do not use in production** as cross-process messaging is not possible and there is data-loss in multi-instance environment.

<!-- External Links -->
[channels-redis]: https://pypi.org/project/channels-redis/
[Docker]: https://www.docker.com/get-started

<!-- File links -->
[settings.py]: ../realtime_chat/settings.py
[docker-compose.yml]: ../docker-compose.yml
