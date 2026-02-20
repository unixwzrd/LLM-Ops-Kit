#!/usr/bin/env bash

. ~/.bash_profile
. ~/.bashrc
. ~/.env

export ELEVENLABS_API_KEY="0f618cf15d1e1c1221663d03b50ee3ed1dfc426527b511d3909a3ad7e51704c0"

nohup /usr/local/bin/openclaw gateway --port 18789 > ~/.openclaw/logs/gateway.log 2> ~/.openclaw/logs/gateway.err.log &
