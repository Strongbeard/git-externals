#!/bin/bash

echo "Installing git hooks"
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

if [ ! -f .venv/bin/activate ]; then
    echo "Creating virtual environment"
    python -m venv .venv
fi

echo "Installing python development dependencies to virtual environment"
source .venv/bin/activate
.venv/bin/python -m pip install --require-virtualenv --upgrade pip
.venv/bin/python -m pip install --require-virtualenv --requirement requirements.txt --requirement requirements-dev.txt

