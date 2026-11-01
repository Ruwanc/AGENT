# Petcare API

<!-- This HTML comment should be removed before embedding. -->

![Build status](https://img.shields.io/badge/build-passing-green.svg)

A small REST API for tracking pet feeding and vet visits. This file has **no frontmatter**, so its title should come from the H1 line above.

## Features

- Track meals per pet, with portion sizes
- Store vaccination dates and reminders
- Export history as CSV

See the [installation guide](guides/install.md) and the [API reference](https://example.com/docs/api "API docs") for details.

## Quick Start

```bash
# clone and install
git clone https://github.com/example/petcare-api.git
cd petcare-api
pip install -r requirements.txt
```

```c
#include <stdio.h>
// "#include" inside code must NOT become a tag
```

Issue #42 and the C# client are mentioned here; in plain Markdown these are not tags.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `DB_URL` | `sqlite:///pets.db` | Database connection string |
| `LOG_LEVEL` | `info` | One of debug, info, warning, error |

## License

MIT
