# Rap Writer · Fresh AI

A Python desktop writing notebook for melodic rap and catchy hooks. Start with your own brief or use **AI Ideas**, then write or revise lyrics against your chosen song structure.

The current version uses an AI draft followed by an AI editing pass. Local checks enforce word rules, section order and line counts before releasing the result. It has no canned lyric bank or offline lyric substitute; writing quality still needs your judgment.

## Run on Windows

Install Python 3.13 with Tcl/Tk and the Python launcher, then open a terminal in this folder:

```bat
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe rap_writer.py
```

The app uses the Python standard library only. After setup, **Start.bat** uses the local virtual environment, or falls back to `py -3.13`. **Launch Rap Writer.vbs** opens the app without a console using an installed Python interpreter. Keep all four Python files alongside the launchers.

Open **Connection** and enter your own OpenAI API key for this session, or provide it through `OPENAI_API_KEY`. Choose a model available to your API account; the source defaults to `gpt-5.5`. Internet access and API credit are required. The application does not include a key or credit.

## Writing flow

- **AI Ideas** fills a fresh topic, emotional details, hook direction and writing controls. Wanted words are empty by default. Recent brief fields help discourage repeated ideas.
- **Write** creates a draft, then edits for relevance, stronger lines, flow and the requested structure. Normal generation uses two API requests, with up to four total when repairs are needed. AI Ideas uses one request, or up to two for a repair.
- **Load song JSON** follows the supplied section names, order and lyric-line targets, including empty instrumental sections. Musical bars and written lyric lines remain separate.
- **New brief** clears topic, details, hook direction and wanted words while keeping the song map, writing settings and current lyric draft.
- **Undo idea** restores the prior brief. Save lyrics as text when you want to keep them.

See [USER_GUIDE.md](USER_GUIDE.md) for word rules, privacy and troubleshooting.

## Local data and API requests

The app creates `settings.json` beside the script for preferences, current brief fields, up to eight recent ideas and AI-field provenance. This file can contain personal writing context and is excluded from this repository. API keys are not saved there. Lyrics are written to disk only when you save them.

Lyric generation sends your brief, word rules and song map to the API, plus the draft when revising. AI Ideas sends current and recent brief fields as repetition exclusions; it does not send the lyric editor contents. Requests set `store` to `false`; this is not a claim about the provider's other retention policies.

## Offline tests

```bat
.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests mock API calls and use fictional fixtures. They check the draft/edit contract, vocabulary gate, cancellation, response handling, imported song maps and idea repetition. They require no API key and spend no API credit.

## Source and license

This repository contains editable application source. Generated exports, private settings, API keys, user audio, bundled runtimes and packaged executables are excluded. Original local releases remain separate. No new license is granted for original application code in this publication; dependency notices retain their own terms.
