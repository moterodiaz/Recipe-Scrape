#!/bin/bash
if [ ! -d .git ]; then
  git init
fi
git add .
git commit -m "chore: initial repository baseline via bootstrap"
