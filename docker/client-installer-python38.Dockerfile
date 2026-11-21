# Test-only legacy interpreter; never part of the server or distributed client.
FROM python:3.8-slim@sha256:1d52838af602b4b5a831beb13a0e4d073280665ea7be7f69ce2382f29c5a613f AS legacy
FROM bearings-development
USER root
COPY --from=legacy /usr/local/bin/python3.8 /usr/local/bin/python3.8
COPY --from=legacy /usr/local/lib/libpython3.8.so.1.0 /usr/local/lib/libpython3.8.so.1.0
COPY --from=legacy /usr/local/lib/python3.8 /usr/local/lib/python3.8
RUN ldconfig && /usr/local/bin/python3.8 --version
USER bearings
