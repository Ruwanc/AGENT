---
title: Installation Guide
tags: setup, install
version: 1.2
updated: 2026-10-01
draft: false
---

# Install the Petcare API

## Requirements

You need Python 3.10 or newer and about 200 MB of free disk space.

## Steps

1. Create a virtual environment with `python -m venv .venv`.
2. Activate it and run `pip install -r requirements.txt`.
3. Start the server with `uvicorn app:main --port 8080`.

> **Note:** on Windows, activate with `.venv\Scripts\activate` instead.

![Architecture diagram](../images/architecture.png)

## Troubleshooting

If the port is already in use, set the `PORT` variable to another value, for example 9090, and start the server again.
