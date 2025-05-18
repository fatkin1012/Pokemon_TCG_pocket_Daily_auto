#!/bin/bash

echo "Creating Python virtual environment if it doesn't exist..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
    source venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "Starting Pokemon TCG Daily Helper..."
python main.py 