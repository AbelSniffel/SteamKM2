# UniKM is out! https://github.com/AbelSniffel/UniKM
### For migration info from SteamKM2 to UniKM, please open the UniKM Github page and scroll to the bottom.

---

# SteamKM2 / Steam Key Manager 2
A Windows desktop application for organizing and managing your game product keys and activation codes. SteamKM2 features Steam integration, database encryption, and a fully themeable UI.

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Python](https://img.shields.io/badge/Python-3.12.10%2B-3776AB?logo=python)
![PySide6](https://img.shields.io/badge/PySide6-6.9.1%2B-41CD52?logo=qt)
![Version](https://img.shields.io/badge/Version-1.9.0-purple)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)


## Overview

SteamKM2 keeps all your game keys in one place: organized, searchable, and secure. Whether you have a handful of codes or hundreds from Humble Bundle, Fanatical, or Green Man Gaming bundles, SteamKM2 gives you a place to store them efficiently. It integrates directly with Steam to enrich your library with cover art, ratings, and tags automatically, and optionally encrypts your database so your keys stay private.

<img width="1952" height="1248" alt="image" src="https://github.com/user-attachments/assets/312c7305-a679-4f8e-8b6d-4f874adfcb07" />

## Features

### Game Library Management
- Add, edit, and delete game entries with title, key, platform, notes, and tags
- Right-click context menu for quick actions: copy key, mark used/unused, fetch Steam data, delete
- Mark games as used or unused with a visual overlay indicator on the game card
- Flag entries as DLC to keep them organized separately from full games
- Attach custom cover images to entries, or let Steam fetch them automatically
- Set expiry/deadline dates

### Views
- Toggle between **Grid** (cover art) and **List** view
- Smooth hover zoom animation on game cards in grid view
- Rating badge on Steam game cards displaying the store review score (Very Positive, Mixed, etc.) with a theme-blended color

### Multi-Select & Batch Operations
- Left-click drag over game cards to rubber-band select multiple entries
- A selection counter bubble appears while dragging to show how many cards are selected
- Apply batch operations across your selection: delete, mark used/unused, or fetch Steam data for all selected games at once
- Clicking a selected card with no modifier held deselects it without clearing the rest of the selection

### Search & Filtering
- Full-text search across titles and keys in the filter bar
- Platform filter dropdown to narrow results to a specific store
- Sort by: Name A-Z, Name Z-A, Platform A-Z, Platform Z-A, and more
- Collapsible **Filters** panel with toggle buttons for: Deadline only, DLC only, Used only, and No Pictures only
- Collapsible **Tags** panel for one-click tag filtering
- Numbered badges on the Filters and Tags buttons show how many active filters are set
- Right-click the Filters or Tags button to instantly clear all active filters

### Platform Auto-Detection
- Automatically identifies the platform from a key's format when you paste it in
- Detects: Steam, Epic Games, Origin/EA, Ubisoft Connect, GOG, Battle.net, Xbox / Microsoft Store, PlayStation, Nintendo, and generic web links

### Steam Integration
- Search the Steam store and auto-fill cover art, title, and release date with a single click
- Fetch ratings directly from Steam's review system
- Sync genre and category tags from SteamSpy for automated labeling
- Batch-fetch Steam data for multiple selected games at once
- Background threaded fetching keeps the UI responsive during network operations
- Cover images and metadata are cached locally to reduce repeated API calls and enable offline browsing
- Editing, adding, and removing games is locked while a fetch is in progress to prevent data corruption

### Context Menu Copy Options
- **Copy Key:** copies the raw key to clipboard
- **Copy Title + Key:** copies a formatted "Title | Key" string
- **Copy Discord Spoiler:** wraps the key in a Discord spoiler tag
- **Copy Redemption Link:** copies the key as a platform redemption URL

### Database Encryption
- AES-256-GCM encryption with PBKDF2 key derivation
- Password prompt on startup when encryption is enabled; nothing is stored in plaintext
- Enable, disable, or change your password at any time from Settings

### Multiple Databases & Backups
- Create new database files or swap the active database from the Settings page
- Merge an external database file into your current one via the Import dialog
- Automatic backups run on a configurable interval
- Manual backups via the Backup / Export dialog with the ability to restore the database
- Configurable maximum backup count to keep storage usage in check

### Import
- **Text File (.txt)** one title/key pair per line
- **Legacy SteamKM1 File (.json / .enc)** imports from the previous SteamKM1 app, including encrypted exports
- **SteamKM2 Database (.db / .db.enc)** restore or merge from a SteamKM2 backup

### Export
- **Standard Backup:** backup in the backups folder, preserves encryption if enabled
- **Text File:** a simple decrypted list of game titles and keys
- **Full Database (Encrypted):** exports the encrypted database file as-is
- **Full Database (Decrypted):** exports a plain SQLite file for use outside the app

### Themes & Customization
- Five built-in themes: **Dark**, **Light**, **Nebula**, **Sunset**, **Ocean**
- Custom theme editor powered by a three-color palette: background, primary, and accent. All other colors are computed automatically
- Adjustable corner radius for cards and scrollbars independently
- Animated gradient bar with four effect modes: **Scroll**, **Pulse**, **Scanner**, and **Heart**
- Toggle style: regular or dot
- Navigation bar position: left, right, top, or bottom
- Navigation bar appearance: Icon & Text, Icon only, or Text only
- Per-card chip visibility settings. Show/hide the title, platform, tags, or deadline chip on each game card

<img width="1952" height="1249" alt="image" src="https://github.com/user-attachments/assets/e0942f47-0460-447d-8a6b-3d59856c2ad4" />


### Notifications & Tooltips
- In-app notification banners for success, error, warning, info, and update events
- Download progress notification with a live progress bar during update downloads
- Custom animated tooltip system with Fade or Slide entrance effects and a configurable show delay

### Health Monitor
- Real-time monitoring of RAM usage (MB and %), CPU usage, thread count, and response time
- Tracks database file size, application uptime, and theme change timing
- Issue log with severity levels (info, warning, error, critical)
- Historical metric graphs for RAM, CPU, and response time over up to 100 data points

<img width="873" height="1095" alt="image" src="https://github.com/user-attachments/assets/a871b288-7193-42c0-9a6f-8cc335b6147c" />

### Built-in Updater
- Automatic update check on launch with a configurable check interval
- Manual "Check for Updates" button on the Update page
- Support for downloading any release version, including previous ones
- Background download with a live progress notification — the UI stays fully usable during the download
- Skip specific versions without being asked again
- Changelog cached locally so it is viewable even without an internet connection
- Configurable update repository (defaults to `AbelSniffel/SteamKM2`)
- Optional **UniKM GitHub** button for migrating to the cross-platform successor app

<img width="1959" height="1246" alt="image" src="https://github.com/user-attachments/assets/4d3bb6cd-7df8-4972-9dac-dd28d230dc22" />

## Requirements

| Dependency | Version |
|------------|---------|
| Python | 3.13+ |
| PySide6 | 6.9.1+ |
| cryptography | 46.0.3+ |
| psutil | 5.9.0+ |

Install dependencies with:
```
pip install -r requirements.txt
```


## Running the App

```
python main.py
```

Or use the included `run.bat` on Windows.


## Migrating from SteamKM1

1. Export your library from SteamKM1 as a `.json` file.
2. In SteamKM2, go to the **Add Games** page and click **Import**.
3. Select **Legacy SteamKM1 File (.json / .enc)** and choose your exported file.
4. SteamKM2 will map all your entries to the new schema automatically.


## Migrating to UniKM

UniKM is the cross-platform successor to SteamKM2, rewritten in Dart and Flutter with support for Windows, macOS, Linux, Android, and iOS.

To migrate:
1. Ensure your SteamKM2 database is **unencrypted** (disable encryption in Settings if needed).
2. Open UniKM and use the **☰ Menu → Import Database** option.
3. Select your SteamKM2 `.db` file. UniKM will import all your entries automatically.
