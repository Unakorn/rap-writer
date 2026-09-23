# User guide

These notes describe the application. For this source checkout, use README.md and Start.bat instead of the original packaged launchers or executable.

```text
RAP WRITER
Melodic verses. Hooks that stay with you.

START HERE
For this source edition, follow README.md and run Start.bat.

1. Describe what you want to say. Add a few details from real life: a place,
   something somebody said, or a small moment that explains the feeling.
2. The defaults are Melodic rap, Reflective / hopeful, Melodic / pocketed
   flow, Internal + end rhymes, and Rapped verses / sung hook. Change them
   for another direction, or start with a short hook to find the song's idea.
3. Add a title or hook phrase if you have one. Keep it short enough to repeat.
4. Pick a length. Full song starts with an 8-line hook, a 16-line verse,
   another 8-line hook, a second 16-line verse, a 4-line bridge and an
   8-line final hook. Song structure lets you change the arrangement.
5. Write, then use Rewrite to ask for a specific change. Undo restores the
   previous version after a rewrite. Copy or Save .txt keeps the lyrics.

AI IDEAS
Click AI Ideas when you want a starting point. It fills the topic, details,
hook phrase and wanted words, plus a matching style, mood, flow, rhyme
approach, imagery and delivery. Each click asks the AI for a fresh direction;
it uses recent suggestions to avoid repeating them. Melodic rap and catchy
hooks remain the main focus, with a variety of subjects and moods.

Edit anything you like, click again for another idea, or use Undo idea to
restore your previous brief and writing settings. Then write in the song
editor yourself, or click Write my lyrics. AI Ideas leaves your current
lyrics, blocked words, length, arrangement and Song JSON in place.
It uses the same Connection as lyric writing. Each click normally makes
one paid API request, with a second request only if the suggestion needs
repair. Stop cancels the idea without applying unfinished results.

WORD FILTERS
Blocked words must stay out. Wanted words are suggestions unless Require all
is enabled. Separate entries with commas, semicolons or newlines. Matching
ignores case and normalizes Unicode; it matches whole words and phrases,
not parts of longer words. Add variants separately when needed.

SONG JSON AND FLOW
Load song JSON accepts Song Structure.json exported by your MIDI builder.
It keeps the section order, timing and instrumental sections. Use Song
structure to review the map and change the lyric-line targets.

A written line is not automatically one musical bar. Flow and delivery
settings guide the writing; they do not generate notes, audio or timed
syllables. Rap or sing the draft over your beat and adjust the phrasing.

CONNECTION
This uses the same connection method as Alternative Rock Writer. It finds
your existing OPENAI_API_KEY, or you can enter a key in Connection for the
current session. The default model is GPT-5.5 and can be changed there.
Writing and AI Ideas need internet access and an OpenAI API key. API usage
is billed separately from a ChatGPT subscription. A song normally uses two requests,
with up to four if the word or arrangement checks need repairs.
Your brief, word lists, song map and lyrics submitted for rewriting are
sent to OpenAI to write lyrics. AI Ideas sends creative settings, word
constraints and recent idea summaries; it does not send your lyric draft.

SAVING
Rap Writer has separate preferences from Alternative Rock Writer. The
executable saves them in Documents\Rap Writer\settings.json. API keys are
never saved there. Lyrics are saved when you choose Save .txt.
Word rules and imported song maps are checked when generating, copying and
saving. Review the line counts of manual arrangements after your own edits.

SOURCE EDITION
The download includes an editable Source folder. Launch Rap Writer.vbs
starts rap_writer.py with Python 3 and Tkinter; no extra
Python packages are needed. Keep lyric_engine.py, idea_engine.py and song_structure.py in
the same folder. Source-edition preferences are saved beside the script.

This is a separate adaptation of your latest Alternative Rock Writer.
Your original writer and its saved settings remain in their own location.
```
