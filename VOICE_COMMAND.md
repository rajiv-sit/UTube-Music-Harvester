# Voice Command Reference

This document summarizes the phrases the built-in voice controller understands today and how they map to actions.

## A. Search & Populate the Table

These phrases fill the search field, execute the existing search flow, and refresh the results table:

- “Search for trance”
- “Search for rock songs”
- “Find jazz music”
- “Play some ambient”
- “Look up Beatles songs”
- “Search YouTube for classical music”

All of these begin with a trigger word (`search`, `find`, `look up`, `play some`) and hand the remaining words to the search UI.

## B. Play a Specific Track (by Title)

When the requested song already appears in the results table, voice commands can start playback directly:

- “Play Shape of You”
- “Play the song Shape of You”
- “Play Blinding Lights”
- “Play the track Rolling in the Deep”

The controller performs a simple substring match (case-insensitive) against the currently listed titles. If no entry matches, the GUI displays “Could not find…”.

## C. Play a Track by Number

Use any of these to reference the queue position exactly:

- “Play track number one”
- “Play track number five”
- “Play the third song”
- “Play song number four”

Numbers map straight to rows (`track 1 → row 0`, etc.) and support both cardinal and ordinal words (e.g., “third”, “fourth”).

## D. Play Everything

Queue and play every result (top-to-bottom) with these hands-free phrases:

- “Play all songs”
- “Play everything”
- “Start playing all”
- “Play the whole list”

When the list is empty, the GUI shows “No songs are available to play.”

## E. Playback Controls

Basic transport commands mirror the existing player buttons:

- “Pause”
- “Resume”
- “Continue”
- “Stop”
- “Next song”
- “Previous song”

These map to pause/play/stop/skip logic so users can stay hands-free once playback begins.

## F. Repeat / Restart (optional curveball)

The current MVP focuses on the commands above, but the framework is ready to add phrases such as “Play again”, “Restart this song”, or “Repeat” once looping is wired up.

## Design Rules & Testing

- Keep phrases short – STT handles them better than long sentences.
- The parser normalizes everything to lower case and matches against a small set of prefixes (search, play, etc.).
- Suggested test phrases: “Search for trance”, “Play all songs”, “Pause”, “Resume”, “Play track number three”, “Play Shape of You”, “Next song”.

With this list in place, the voice controller drives the existing search/track controls without needing a full NLP stack, which keeps behavior predictable.
