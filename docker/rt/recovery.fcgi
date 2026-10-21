#!/bin/sh
# Separate FastCGI process pool. Browser headers cannot select this configuration.
export BEARINGS_RT_RECOVERY=1
exec /usr/share/request-tracker5/libexec/rt-server.fcgi
