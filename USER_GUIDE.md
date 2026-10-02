# Using Rap Writer

## First launch

Follow the Python setup in [README.md](README.md), then run **Start.bat**. The window should say **Rap Writer · Fresh AI**. The optional VBS launcher opens the same script without a console, using Python installed on your computer.

Open **Connection**, enter a session API key or use `OPENAI_API_KEY`, and select a model available to your account. The key is not saved in the app's preferences. Requests are billed by the API provider.

## Start a brief

Write what the song is about in **Topic**. Use the details field for feelings, intentions, relationships, facts or a story direction. You do not need to invent a location or list objects. A hook phrase is optional.

**AI Ideas** proposes a new brief and writing controls. It does not write the song immediately. Review and edit the suggestions, then press **Write**. Wanted words are empty by default so an AI suggestion does not force an object or setting into the lyrics.

The app remembers up to eight recent ideas to discourage repeated hooks, situations and distinctive details. It cannot guarantee that every response will feel original. **Undo idea** restores the preceding brief. **New brief** clears topic, details, hook phrase and wanted words without deleting your current lyric draft, song map or writing settings.

When you change an AI-created brief, unchanged AI-suggested wanted words are cleared. Wanted words you have edited yourself remain. A visible summary above **Write** shows which wanted words are active.

## Shape the song

Select the style, mood, phrasing, rhyme style, dynamics and imagery you want. The default full song is:

| Section | Lyric lines |
| --- | ---: |
| Hook | 8 |
| Verse 1 | 16 |
| Hook | 8 |
| Verse 2 | 16 |
| Bridge | 4 |
| Final hook | 8 |

Other presets and custom section lists are available. A custom arrangement uses one `Section name: lines` row per section. These counts mean written lyric lines, not exact musical bars or timing.

**Load song JSON** accepts the supported `16bar.song_structure` version 1 format. **View song map** lets you inspect it. The generator follows its exact section names, order and lyric-line targets. Instrumental sections retain their headings with no lyrics underneath. An entirely instrumental map needs at least one section changed to lyrics before writing.

## Word rules and revisions

Blocked words and phrases are checked locally before lyrics appear. Matching handles case, accents, invisible formatting and punctuation boundaries; whole words are used, so blocking `wire` does not block `wireless`.

Some recurring unwanted imagery is always blocked in this edition, including orange chairs, soda or vending machines, and laundromat/laundry-mat variants. Other blocked words remain editable. Conflicting required and blocked words are rejected before an API request.

Wanted words are optional suggestions unless **Require all** is selected. Do not use them as a list of mandatory objects unless you want those objects in the song. The first launch with older preferences also clears legacy wanted-word lists containing the retired imagery.

Writing normally makes a draft request and an editing request. The editor uses your current brief and structure as the source of truth, removes unrelated invented premises and strengthens weak lines. Up to two further repair requests are allowed if local checks fail. If the result still breaks the rules, it is not released. There is no offline lyric fallback.

For revisions, the existing lyrics and revision instructions are sent with your settings. Cancellation stops later work and prevents an unfinished result from replacing your draft; it cannot undo a request already sent to the API.

## Saving and privacy

Use **Save .txt** to keep a lyric draft. Closing with unsaved edits prompts before discarding them.

The app saves preferences, brief fields, recent idea history and AI-field provenance in `settings.json` beside the script. That file is private local data and is not included here. The settings writer does not store the API key or lyric editor contents. AI Ideas sends brief fields as repetition exclusions, but does not send existing lyrics or revision instructions. Lyrics generation and rewriting do send the writing context needed for those requests.

Do not commit settings, saved lyrics or credentials when making your own copy of this repository. Keep a separate backup of writing you want to preserve.

## If something fails

- **Python or Tk cannot be found:** install Python with Tcl/Tk, or launch from the virtual environment described in the README. Start.bat leaves a failed launch visible for troubleshooting.
- **API key or model rejected:** check **Connection**, model access and billing for your API account.
- **No lyrics released:** review conflicting word rules, required words and line targets. Try a clearer brief or fewer required words.
- **Ideas feel repetitive:** check the topic, details, hook and visible wanted-word summary. Use **New brief** to clear those fields, then request or write a new direction.
- **Source updates do not appear:** close the existing window and launch again. A running Python process keeps the code it loaded earlier.

Local validation checks structure and vocabulary. It cannot promise great lyrics, exact bar timing or a particular emotional effect; read, revise and perform the result to judge its fit.
