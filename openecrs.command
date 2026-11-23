#!/bin/bash
cd "$(dirname "$0")"
exec python3 code/agent_app.py --open
