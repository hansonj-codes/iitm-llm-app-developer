#!/bin/bash
set -e  # exit if any command fails

# --- Run your startup commands ---
git config --global user.email "$GIT_AUTHOR_EMAIL"
git config --global user.name "$GIT_AUTHOR_NAME"

# --- Run the CMD from Dockerfile ---
exec "$@"
