# SELF BOT DISCORD

Windows desktop configuration panel, version 2.8.

**[Español](README.es.md)** · **[English guide](docs/guide.en.md)** · **[Guía en español](docs/guide.es.md)**

Configure channels, a message, an optional image and a schedule. Export a Discloud ZIP or a standalone Windows package with a desktop BAT launcher and live CMD logs. Load previously generated BAT/ZIP packages to edit and update them.

## Features

- English and Spanish interface; light and dark themes.
- Fixed-size window with scrolling and a text/image preview.
- Add channels individually and identify their channel/server names.
- Tokens with or without surrounding quotes.
- Discloud export and automatic local desktop launcher creation.
- Exported instructions and runtime logs follow the selected language.
- Load and update packages created by this program without executing imported BAT files.
- Local drafts protect the credential with Windows DPAPI.

## Run from source

Requires Windows, Python 3.10+ with Tkinter, and Pillow.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/build.py
.\.venv\Scripts\python.exe app.py
```

The build creates `local-runner.exe` for local exports and the desktop application in `dist/`. See the [English guide](docs/guide.en.md) for usage, package updates and troubleshooting.

## Account and credential notes

This version uses a **personal account token**. Discord prohibits automated normal user accounts outside its bot/OAuth2 API and may terminate affected accounts; see [Discord's official explanation](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots). This project does not provide a way to bypass Discord protections. For supported automation, use an official bot account; this panel would need adaptation for that workflow.

Generated BAT/ZIP packages contain a plaintext credential in `config.json`. Never commit or share those packages, screenshots containing tokens, or personal configuration files. Opening the panel or importing a package does not send messages. Starting a generated runtime begins the first round immediately.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic credentials and do not contact Discord. Source files, documentation and an example configuration are included; executables and personal data are excluded from Git.
