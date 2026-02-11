# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mylar3 is an automated comic book (CBR/CBZ) downloader for NZBs and torrents, written in Python. It monitors comic series for new issues, handles downloading from multiple sources, and manages post-processing (sorting, renaming, meta-tagging).

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (web UI at http://localhost:8090)
python Mylar.py

# Common flags
python Mylar.py --nolaunch          # Don't open browser on startup
python Mylar.py --port 8091         # Custom port
python Mylar.py -v                  # Verbose/debug logging
python Mylar.py -q                  # Quiet mode
python Mylar.py -d --pidfile /tmp/mylar.pid  # Daemon mode
python Mylar.py --datadir /path     # Custom data directory
python Mylar.py --config /path/config.ini    # Custom config file

# Maintenance mode (no GUI)
python Mylar.py maintenance --exportjson output.json
python Mylar.py maintenance --importdatabase mylar.db
python Mylar.py maintenance --importjson input.json
python Mylar.py maintenance --carepackage
python Mylar.py maintenance --fixslashes
python Mylar.py maintenance --clearprovidertable
```

## Testing

There is no formal test framework (no pytest, unittest, or CI/CD). There are no linting or formatting configurations.

## Architecture

### Tech Stack
- **Web framework**: CherryPy (port 8090 default, 10-thread pool)
- **Templating**: Mako templates (in `data/interfaces/`)
- **Database**: SQLite3 (`mylar.db` in data directory)
- **Scheduling**: APScheduler (background jobs)
- **Config**: INI-based (`config.ini` via `configparser`)

### Entry Point & Startup Flow
`Mylar.py` is the main entry point. On startup it:
1. Validates Python dependencies against `requirements.txt`
2. Parses CLI arguments
3. Calls `mylar.initialize(config_file)` — loads config, checks/updates DB, initializes logger
4. Calls `mylar.start()` — sets up APScheduler jobs and queue workers
5. Starts the CherryPy web server via `mylar/webstart.py`

### Key Modules (under `mylar/`)

| Module | Purpose |
|--------|---------|
| `__init__.py` | Global state, `initialize()` and `start()` functions, scheduler setup, queue definitions |
| `webserve.py` | CherryPy route handlers (`WebInterface` class) — largest module (~9,700 LOC) |
| `api.py` | REST API (`Api` class) with 40+ commands |
| `config.py` | Configuration management with `_CONFIG_DEFINITIONS` dict; INI sections: General, Scheduler, Weekly, Interface, API, CV, Logs, etc. |
| `db.py` | SQLite wrapper — `fetch()` for reads, `action()` for writes, `upsert()` for upserts; thread-safe with `db_lock` |
| `search.py` | Core search logic, provider integration, download queue management |
| `PostProcessor.py` | Post-processing: file validation, extraction, renaming, metadata correction |
| `updater.py` | Database synchronization and series metadata updates |
| `cv.py` | ComicVine API integration |
| `helpers.py` | Utility functions (~5,000 LOC) |
| `filechecker.py` | File system operations and validation |
| `importer.py` | Comic library import and batch operations |
| `rsscheck.py` | RSS feed monitoring |
| `weeklypull.py` | Weekly pull list tracking |
| `getcomics.py` | GetComics.org direct download integration |
| `notifiers.py` | Notification dispatch (Prowl, Pushover, Slack, Mattermost, etc.) |
| `cmtagmylar.py` | ComicTagger integration for metadata tagging |

### Download Clients

**Torrent clients** (`mylar/torrent/clients/`): Deluge, qBittorrent, rTorrent, Transmission, uTorrent

**Direct download** (`mylar/downloaders/`): MEGA, MediaFire, PixelDrain, external server

**Usenet**: SABnzbd (`sabnzbd.py`), NZBGet (`nzbget.py`)

### Background Jobs (APScheduler)
Configured in `mylar/__init__.py start()`:
- **dbupdater**: Watchlist DB update (default 1440 min)
- **search**: Auto-search for wanted issues (configurable)
- **weekly**: Pull list fetch (every 4 hours)
- **rss**: RSS feed checking (default 20 min)
- **version**: GitHub update check (default 360 min)
- **monitor**: Download folder monitoring (default 5 min)

Queue workers: `SNATCHED_QUEUE`, `NZB_QUEUE`, `SEARCH_QUEUE`, `PP_QUEUE`, `DDL_QUEUE`

### Web UI
Two interfaces under `data/interfaces/`: `default` (legacy) and `carbon` (primary). Static assets (CSS, JS, images) are served from `data/`.

### Bundled Libraries
`lib/` contains vendored third-party code: `comictaggerlib`, `configobj`, `deluge_client`, `mega`, `natsort`, `qbittorrent`, `rarfile`, `rtorrent`, `transmissionrpc`, `utorrent`, etc. The `lib/` directory is added to `sys.path` at startup.

### REST API
Endpoint: `http://host:port/api?apikey=KEY&cmd=COMMAND`
Returns JSON. See `API_REFERENCE` for full command list.

## Adding New Functionality

- **New config options**: Add to `_CONFIG_DEFINITIONS` in `mylar/config.py`
- **New web routes**: Add methods to `WebInterface` in `mylar/webserve.py`
- **New API commands**: Add to the `Api` class in `mylar/api.py`
- **New background jobs**: Configure in `mylar/__init__.py`'s `start()` function
- **New download providers**: Add provider logic in `mylar/search.py` or under `mylar/downloaders/`
- **New torrent clients**: Add a module under `mylar/torrent/clients/`
