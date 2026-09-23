# Rap Writer

A Windows lyric-writing app focused on melodic rap and catchy hooks. AI Ideas fills a fresh creative brief; the lyric editor supports generation, rewriting, word rules, song-structure JSON, and undo.

## Run from source (Windows)

Install Python 3.13 with Tkinter and the Windows Python launcher, then run in this folder:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe rap_writer.py
```

After setup, `Start.bat` uses the local `.venv`. See [USER_GUIDE.md](USER_GUIDE.md) for controls and workflow.

Set your own `OPENAI_API_KEY` environment variable or enter a key in Connection for the current session. API use incurs charges through your own account. Briefs and writing requests go to OpenAI; keys and personal preferences are not part of this repository. The model is configurable in Connection.

## Source and distribution

This repository contains editable application source. Generated exports, private settings, API keys, user audio, bundled runtimes and packaged executables are excluded. Original local releases remain separate. No new license is granted for original application code in this publication; dependency notices retain their own terms.

## Optional Windows executable

From the configured environment, install PyInstaller and build:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --windowed --name "Rap Writer" rap_writer.py
```

Review dependency redistribution notices before distributing a binary.
