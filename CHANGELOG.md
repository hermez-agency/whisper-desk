# Changelog

## Unreleased

### Added

- **Writing styles** (Wispr Flow's Styles): `style` in `[model]`, or **Style** in the
  settings window. `"formal"` (the default) writes the dictation as Whisper punctuates it;
  `"casual"` without the full stop that ends it, as in a chat message — *"Ça marche. On se
  voit demain"*; `"very_casual"` without it nor the capital each sentence opens on — *"ça
  marche. on se voit demain"*. As you dictate, each sentence is typed without its full stop,
  which comes before the next sentence if you go on. Question and exclamation marks,
  ellipses and an abbreviation's full stop stay; names of the vocabulary and replacements,
  acronyms, mixed-case names, English *I* and snippets keep their capitals (`style.py`).
- **Lower latency** (Wispr Flow's "4× faster than typing"): a sentence is at the cursor about
  when the pause that ends it does, instead of a transcription later. The model starts on
  the sentence 0.3 s into the pause, from the very sound the pause then sends; when the
  pause reaches 0.6 s (`segment_silence_seconds`) its text is ready, and if you speak again
  first that early pass is dropped and the sentence goes on (`Recorder.on_draft`, the
  daemon's `Draft`). The shortcut pressed during that pause hands the sentence already in
  the model over. The sentence now ends 0.3 s after its last voice (the margin it was
  meant to keep), so that the early pass and the sentence are the same sound. The model is
  also run once on silence as soon as it is loaded: the first sentence of the day no longer
  pays twice the time for the first pass.
- `bench/latency/measure.py`: 27 dictations of three sentences made from the control
  recordings, played in real time into the daemon's own dictation, the time from the end of
  each sentence's voice to its text, against another copy of whisper-desk (`--src`):
  - faster-whisper `large-v3-turbo` (CUDA, float16): sentence ended by a pause, median
    1.11 s → 0.76 s; first sentence after the load 1.43 s → 0.83 s; last sentence, shortcut
    pressed 1.2 s after it 1.10 s → 0.78 s, 0.45 s after 0.95 s → 0.77 s, 0.2 s after
    0.70 s → 0.68 s; word error rate 4.9 % → 4.7 %;
  - faster-whisper `small` (CPU, int8): 2.14 s → 1.79 s; first sentence 2.19 s → 1.82 s;
    shortcut 1.2 s after 2.21 s → 1.87 s, 0.45 s after 2.07 s → 1.93 s, 0.2 s after
    1.81 s → 1.86 s; word error rate 6.1 % → 5.2 %.
  The cost: the early passes of pauses the voice goes on after — 96 passes through the
  model for 54 sentences, 63 before (the same on the GPU and the CPU).
- **Replacements learned from a correction** (Wispr Flow's dictionary fed by what you
  correct): a name already in `vocabulary` that Whisper still writes wrong is beyond what
  the vocabulary can do — corrected in the history (**Correct…**, `whisper-desk history
  --correct`), what Whisper wrote is saved with the name in `[replacements]`, and written
  right from then on: *"le ticket ouvert par Opal"* corrected into *"…par Opoil"* saves
  `"Opal" = "Opoil"`. A name not yet in the vocabulary joins it first, as before; the
  window and the command say which replacements were saved, *Add the corrected names and
  words to the vocabulary* unticked (`--no-learn`) saves none. Only a run of three words
  at most that sounds like the name is taken: a change of mind (*OVH* → *Scaleway*), an
  ordinary word put for another (*pool* → *pull*), a word of one or two letters, a term of
  the vocabulary itself or a misspelling that already has an entry — one switched off
  included — never are (`vocabulary.misheard`, `vocabulary.learn_spellings`).
- `bench/dictionary/measure.py --from-corrections`: the replacements are those
  whisper-desk takes on its own from the second correction of each first dictation,
  instead of the misspellings picked out by hand of `--replacements`; and the 46 written
  corrections are read again with their names already in the vocabulary (a new
  `replaced` column says which replacement each should give):
  - written corrections: 25/26 replacements wanted taken, none unwanted, 16/16 grammar
    fixes and changes of mind take none (the one missed: *C plus plus* → *C++*, too unlike);
  - faster-whisper `small` (CPU, int8): name written right in the other sentence 5/22 →
    17/22, word error rate 18.1 % → 8.0 % — the same as the replacements picked by hand;
  - faster-whisper `large-v3-turbo` (CUDA, float16): 9/22 → 18/22, 15.2 % → 8.0 % — the
    same as by hand;
  - the 8 control sentences: no replacement changed any (one loses a sentence start's
    capital to the vocabulary, as without the replacements).
  Taken on the way and worth knowing: *Leads* → *Leadz* and *au poil* → *Opoil*, ordinary
  words a replacement then rewrites everywhere — they can be removed in the settings.
- **French and English in one dictation** (Wispr Flow's language switching): with
  **French and English** as the language in the settings window (and the first-launch
  window), or `language = "fr, en"` in `[model]`, each sentence is written in the language
  it was said in, and never in a third one. Whisper weighs every language it knows for the
  sentence, and the most likely of those listed is kept: with `"auto"`, a short *"Oui."*
  came out in Spanish or Japanese and *"Check tes mails."* in Russian or Turkish; with
  `"fr"` alone, an English sentence came out in French (*"Thanks a lot."* written
  *"Merci beaucoup."*). Any codes go, two or more (`"de, en"`, `"fr, en, es"`); an
  English-only model keeps the first one. The default stays `"fr"`.
- `bench/languages/`: 50 short replies (half of the French ones laden with English words,
  *"Je push le fix ce soir"*) recorded with the voices of the other benches, and the 84
  control recordings, each set dictated as one dictation switching between French and
  English, once per `language` setting. Sentences transcribed in a language other than
  the one spoken, out of 134 — `"fr"` / `"auto"` / `"fr, en"`:
  - faster-whisper `large-v3-turbo` (CUDA, float16): 60 / 2 / **0**; word error rate,
    short replies 14.4 % / 12.2 % / 13.3 %, ordinary sentences 7.6 % / 7.0 % / 7.0 %;
  - faster-whisper `small` (CPU, int8, one thread): 60 / 2 / **1** (a lone *"Oui."*
    written *"Ui."*, in English); short replies 23.2 % / 7.2 % / 7.7 %, ordinary sentences
    13.7 % / 5.4 % / 5.4 %.
  Telling the language costs what `"auto"` costs: about twice the time per sentence of a
  forced language on one CPU thread (8.2 s against 4.3 s), 0.6 s against 0.3 s on the GPU.

- **Replacements in the personal dictionary** (Wispr Flow's "Correct a misspelling"): a
  name Whisper never writes right, even with it in `vocabulary`, is saved with what Whisper
  writes for it — `"alarmor" = "Ollama"`, `"mac os" = "macOS"` — in the new
  `[replacements]` section of `config.toml` or the **Replacements** list of the settings
  window (**Add…**, **Edit…**, **Remove**), and it is written your way wherever it
  appears. The misspelling is matched as whole words, whatever their case, spaced or
  hyphenated, never inside a longer word, before the *'t* of a contraction or across a
  full stop; the longest entry wins. The spelling is written as saved (*macOS*,
  *iPhone*), unless it is all in lowercase: then it takes a sentence start's capital
  (*"don't" = "do not"* gives *Do not*). Applied by local rules (`replacements.py`) right
  after the transcription, before the lists and the snippets, so the model hears the name
  as you spell it in the context of the next sentence. Two entries with the same
  misspelling are refused; an empty spelling switches an entry off.
- `bench/dictionary/measure.py --replacements`: each first dictation of the bench is said
  again with the vocabulary learned from its correction, and what Whisper still writes
  instead of the name is saved as a replacement; the name is then said in another
  sentence:
  - faster-whisper `small` (CPU, int8): name written right 14/22 with the vocabulary alone
    → 17/22 with the replacements (5/22 with neither), word error rate 10.9 % → 8.0 %;
  - faster-whisper `large-v3-turbo` (CUDA, float16): 16/22 → 18/22 (9/22 with neither),
    9.4 % → 8.0 % (the vocabulary-alone figure is #34's: the GPU dropped out before it
    could be measured again);
  - the 8 control sentences: no replacement changed any.
  What remains is Whisper writing the name differently from one sentence to the next
  (*Ananaling*, then *Animal Inc.*; *Pono*, then *Polos*). Two of the entries saved are
  ordinary words (*au poil*, *leads*), which a user should not save: replacements are
  literal.
- **Dictating under your breath** (Wispr Flow's "works when you're whispering"): speak low
  or whisper close to the microphone, in an open space or next to someone asleep, and the
  dictation goes on as usual — nothing to switch on. Three changes, all local:
  - the automatic threshold stops at an RMS of 60 instead of 180 (`MIN_THRESHOLD`), so a
    voice some 25 dB under an ordinary one opens the listening; the noise of the room
    still raises it through the calibration of the first 400 ms;
  - once a sentence has begun, a voice down to 60 % of the threshold holds it open: the
    soft syllables of a low voice no longer pass for the pause that ends a sentence;
  - a sentence said low is raised to the level of an ordinary voice (at most +30 dB,
    never into clipping) before faster-whisper and its voice detector hear it; a voice
    already loud enough reaches the model untouched.
  Noises that now reach a low voice's threshold (a door, a keyboard) can be kept out with
  `threshold = 180` in `[recording]`, which hears about as before.
- `bench/whisper/`: the 84 control recordings of the other benches, French and English,
  played at an ordinary level, 24 dB lower and whispered (the voice's envelope over a
  noise) at that low level, over the noise of a quiet room, through the `Recorder` and
  then the `Transcriber` as the daemon does:
  - sentences heard whole by the recorder: low 3/84 → 81/84 (81 missed before),
    whispered 5/84 → 83/84, ordinary 83/84 → 84/84;
  - faster-whisper `large-v3-turbo` (CUDA, float16), word error rate: low 97.6 % →
    4.3 % (0/84 → 70/84 exact), whispered 97.2 % → 6.2 % (0 → 61/84), ordinary 3.6 % →
    3.6 %;
  - faster-whisper `small` (CPU, int8): low 97.5 % → 7.7 % (0 → 59/84), whispered
    97.6 % → 13.1 % (0 → 53/84), ordinary 6.0 % → 6.5 % (69 → 67/84 exact);
  - two sentences said 1 s apart: still split at the pause and ended by the silence
    (ordinary 42/42 before and after, steady room or noise swelling by 10 dB; low 0/42 →
    40/42), and 40 recordings of room noise alone, steady or fluctuating, heard 0/40
    before and after, no text written.
- **Automatic updates**: a user timer (systemd `whisper-desk-update.timer`, launchd
  `fr.whisperdesk.update` on macOS) runs the new `whisper-desk update --auto` once a day —
  `Persistent=true` and a random delay of up to an hour —, installed by `install.sh` and
  removed by `uninstall.sh`. A new version is installed through the usual `install.sh`
  replay, shortcut and configuration kept, and announced in a notification (*updated* /
  *update available*); nothing is said when there is nothing new, and offline is silent
  until the next round. It never runs during a dictation: it is retried 30 minutes later
  (systemd). `auto_update` in the new `[update]` section of `config.toml`, and **Updates**
  in the settings window, choose `"install"` (default), `"notify"` or `"off"`. An
  installation made from a clone is left alone.
- **A personal dictionary fed by your corrections** (Wispr Flow's dictionary, which learns
  the words you correct): **Correct…** in the history window — or `whisper-desk history
  --correct N "text"` — fixes the text of a dictation, and the words you corrected join
  `vocabulary`, the names and jargon pushed into the decoder, so that they come out right
  the next time. Correct *"le devis d'animal link"* into *"le devis d'Animalink"* once and
  the next *Animalink* is written so. A name or a piece of jargon is learned — a capital a
  sentence start does not explain, a digit, a sign (*Node.js*, *C++*, *faster-whisper*
  where *faster whisper* was heard) —, as is a word of five letters or more heard as one
  that sounds like it (*ripos* → *repos*); the elision and the possessive are left out
  (*d'Animalink*, *Animalink's* teach *Animalink*). A grammar fix (*mange* → *mangent*,
  *a* → *à*, *has* → *have*), a short word, a word Whisper left out and a change of mind
  (*matin* → *après-midi*) teach nothing; a sentence reworded teaches only its names. The
  window and the command say which words were added and the daemon is reloaded; a word
  already in the vocabulary, in any case, is not added twice. Untick *Add the corrected
  names and words to the vocabulary* (`--no-learn`) to fix the text alone; the words are
  removed in **Settings** like the others. Local rules (`vocabulary.py`), nothing leaves
  the machine.
- `bench/dictionary/`: 46 corrections written (30 that should teach a word, 16 that
  should not) and 22 names said in French and English, each once in a dictation corrected
  as in the history, then in another sentence, with 8 control sentences:
  - written corrections: 30/31 wanted words learned, none unwanted, 16/16 controls teach
    nothing (*pool* → *pull* is missed: four letters, as short as *has* → *have*);
  - faster-whisper `small` (CPU, int8): the name written right in the next sentence 5/22 →
    14/22, word error rate 18.1 % → 9.4 %; controls 3.4 % → 5.2 % (*œufs* written
    *oeufs*);
  - faster-whisper `large-v3-turbo` (CUDA, float16): 9/22 → 16/22, 15.2 % → 9.4 %;
    controls 3.4 % → 3.4 %.
  Of the names misheard in the first dictation, 19/19 (`small`) and 13/14
  (`large-v3-turbo`) were learned from the correction; what remains is Whisper not
  hearing the name even with it in the vocabulary (*Opoil* heard "au poil", *Hostinger*
  "au Stinger"), and two ordinary words learned from a real correction (*tableau* for
  "tabou", *lives* for "lies").
- **Numbered lists said aloud** (Wispr Flow's lists): the items you number as you say
  them are written as a list, one per line — *"J'ai trois choses à acheter, un, des œufs,
  deux, du lait et trois, du pain"* is written "J'ai trois choses à acheter :" then "1. Des
  œufs", "2. Du lait", "3. Du pain". Numbers (*un, deux*, *one, two*), ordinals
  (*premièrement, deuxièmement*, *primo, secundo*, *firstly, secondly*, *first, second*),
  *numéro* / *number* and the figures Whisper writes for them (*1. Le bilan 2. Le
  recrutement*) all count. The words before the first item become its title, with a colon
  (a space before it in French); what is said after the last item, once its sentence is
  over, goes on the next line; the *et* / *and* between two items and their commas go. A
  list needs two items numbered in a row from one — three when Whisper drops the pause
  after the numbers (*un des œufs, deux du lait*) —, so that numbers said in a sentence stay
  words: *j'en veux deux, trois si possible*, *un, deux, trois, soleil*, *first, let me
  check the logs*. With the as-you-go dictation you can pause after each item: the next
  number goes on the list already at the cursor, and a sentence that may open a list
  (*Premièrement, …*) waits for the next one before it is inserted, one sentence at most.
  Local rules (`lists.py`); `lists = false` in `[model]` keeps the words.
- `bench/lists/`: 20 lists said in French and English and 10 control sentences, with
  synthetic recordings, each run whole and cut after each sentence. Lists laid out exactly
  (same lines, same numbers) and error rate on words, line breaks and item numbers, before
  → after:
  - written sentences: 0/20 → 20/20; FR 33.0 % → 0.5 %, EN 37.3 % → 0.0 %;
  - faster-whisper `small` (CPU, int8): 0/20 → 18/20; FR 33.0 % → 8.9 %, EN 36.4 % → 4.2 %;
  - faster-whisper `large-v3-turbo` (CUDA, float16): 0/20 → 18/20; FR 28.1 % → 5.4 %, EN
    37.3 % → 9.3 %.
  The same whole and cut; no control sentence changes. What remains is the transcription:
  numbers Whisper does not write, *secundo* heard as "ce qu'un dos".
- **Usage statistics** (Wispr Flow's Insights): `whisper-desk stats` prints the
  dictations and the days they were made on, the words dictated — in all, today and over
  the last 7 days —, the speed in words per minute and the days in a row with a dictation,
  the current streak and the best one. Everything is worked out from the history on the
  spot, on this machine; nothing is sent or stored besides. The marks said aloud are not
  counted as words, the speed only counts the dictations whose listening time was
  recorded, and a streak that reached yesterday still holds until today is over.
  `--json` gives the same figures as one JSON object, for a script or a status bar. The
  apps dictated into and Wispr Flow's rank among its users are not shown: the history
  does not record the app, and there are no other users to compare with offline.
- **Quotes and brackets said aloud** (Wispr Flow's spoken punctuation, continued):
  *ouvrez les guillemets* … *fermez les guillemets* are written « … », *ouvrez la
  parenthèse* … *fermez la parenthèse* ( … ), *open quote* … *close quote* (or *end
  quote*, *quote* … *unquote*) "…" and *open paren* … *close paren* (or *parenthesis*)
  ( … ): "Il m'a dit ouvrez les guillemets je reviens demain fermez les guillemets" is
  written "Il m'a dit « je reviens demain »". The commas Whisper puts around the commands
  for the pause go, as do the « » it sometimes writes around them; a question or an
  exclamation said before the closing stays inside. The forms Whisper hears for the
  imperative (*ouvré*, *fermé*, *ouvrait*) count; the words said in a sentence stay words
  (*il est temps de fermer la parenthèse*, *on ferme la parenthèse*, *can I quote you*,
  *an open quote request*, *quote unquote*), unless their other half is said too. A quote
  opened before a pause closes in the next sentence without a stray space. Same switch
  as the rest of the spoken punctuation, `spoken_punctuation` in `[model]`.
- `bench/punctuation/`: 16 sentences with quotes or brackets and 8 control sentences
  added (44 + 22 in all). Error rate on words and marks on the 16 new sentences, before →
  after:
  - written sentences: 53.1 % → 0.0 %, 16/16 exact;
  - faster-whisper `small` (CPU, int8): 70.1 % → 35.4 %, 3/16 exact;
  - faster-whisper `large-v3-turbo` (CUDA, float16): 86.4 % → 18.4 %, 4/16 exact.
  The 28 earlier sentences and the 22 controls do not change. What remains is the
  transcription of the synthetic voices — *parenthèse* heard as "l'apparentaise",
  *paren* as "Perenn" — and the full stop Whisper ends each sentence with.
- **Punctuation said aloud** (Wispr Flow's spoken punctuation): *virgule*, *point*,
  *point d'interrogation*, *point d'exclamation*, *point-virgule*, *deux points*, *à la
  ligne*, *nouveau paragraphe* — and *comma*, *period*, *full stop*, *question mark*,
  *exclamation mark*, *semicolon*, *colon*, *new line*, *new paragraph* — are written as
  the mark or the line break they name: "Bonjour Marie virgule à la ligne merci point" is
  written "Bonjour Marie," then "Merci." on the next line. Whisper's own punctuation around
  the word gives way, French marks get their space, and a full stop or a line break
  capitalises what follows. The words said as words stay: after an article (*une
  virgule*, *le point*, *a new line of products*), in a number (*trois virgule cinq*),
  before what makes them a noun (*deux points d'avance*), and *point* or *period* anywhere
  a full stop cannot stand (*mon point de vue*, *a good point, let me think*). A mark said
  after a pause, alone in its sentence, is glued to the sentence before, and nothing is
  put in front of what follows a line break. Local rules (`punctuation.py`), applied last;
  `spoken_punctuation = false` in `[model]` keeps the words.
- `bench/punctuation/`: 28 sentences that say a mark or a line break and 14 control
  sentences, with synthetic recordings. Error rate on words and marks against the expected
  text, before → after:
  - written sentences: 33.6 % → 0.0 %, 28/28 exact; controls 0 % → 0 %;
  - faster-whisper `small` (CPU, int8): 51.0 % → 19.8 %, 11/28 exact; controls
    unchanged (7.0 %, transcription slips);
  - faster-whisper `large-v3-turbo` (CUDA, float16): 45.8 % → 9.9 %, 15/28 exact;
    controls unchanged (5.2 %).
  What remains is mostly the transcription: the commas Whisper adds on its own ("Hi,
  John,"), *comma* heard as "come a", *point-virgule* as a comma, *prêt virgule* as
  "pré-virgule".
- **Snippets in the settings window** (Wispr Flow edits its snippets in the app): a
  **Snippets** list in `whisper-desk settings` shows each cue with its text, and
  **Add…**, **Edit…** and **Remove** change them without opening `config.toml` — the text
  may hold several lines. **Save** rewrites only the `[snippets]` section, its comments
  and the rest of the file kept, and the daemon takes the change at once. Two cues
  whisper-desk would hear the same (*Mon adresse.* and *mon adresse*), a text without a
  cue, or a cue made of punctuation alone are refused with a message, and nothing is
  written.
- **Hesitations left out** (Wispr Flow's *filler removal*): the *euh*, *heu*, *hum*,
  *hmm*, *um*, *uh*, *erm* Whisper writes down go, with the commas of the pause around
  them, and a word or a run of up to three words said twice in a row is written once —
  "Je je pense, euh, qu'on devrait" is written "Je pense qu'on devrait", "We could, we
  could meet" is written "We could meet". Words that only look like hesitations (*eu*,
  *ah*, *Ben*, *err*) and the doubles the language means (*nous nous*, *très très*,
  *that that*, *had had*, numbers) stay. Local rules (`hesitations.py`), applied after
  the corrections said aloud; `hesitations = false` in `[model]` turns them off.
- `bench/hesitations/`: 26 sentences with a hesitation or a stuttered word and 14 control
  sentences, with synthetic recordings. Word error rate against the expected text,
  before → after:
  - written sentences: 19.7 % → 0.0 %, 26/26 exact; controls 0 % → 0 %;
  - faster-whisper `small` (CPU, int8): 15.7 % → 5.6 %, 17/26 exact; controls
    unchanged (5.9 %, transcription slips);
  - faster-whisper `large-v3-turbo` (CUDA, float16): 13.5 % → 3.4 %, 20/26 exact;
    controls unchanged (3.5 %).
  What remains is mostly the synthetic voice: its *euh* comes back as "A", "« E »" or
  "O", which no rule can tell from a word.
- **Snippets** (Wispr Flow's *snippets*): a cue said aloud is replaced by the text saved
  for it in the `[snippets]` section of `config.toml` — "mon adresse perso" types the
  address, "ma signature" a signature on several lines. Alone, the cue gives the text
  exactly as saved; inside a sentence, only the cue is replaced. Case, punctuation and
  spacing do not matter, a cue never matches inside a longer word, the longest cue wins.
  Applied locally after the transcription (`snippets.py`); the model's context keeps
  the words that were said, not the text that replaced them.
- `bench/snippets/`: 20 sentences that say a cue and 10 control sentences that come
  close, with synthetic recordings. Sentences whose snippets all reach the text, before →
  after: written sentences 0/20 → 20/20; faster-whisper `small` (CPU) 0/20 → 18/20;
  `large-v3-turbo` (CUDA) 0/20 → 18/20, 20/20 with the cues also in the decoder
  (`--hotwords`, as `vocabulary` does). Controls changed for nothing: 0/10 everywhere.
- **Corrections said aloud are carried out** (Wispr Flow's *backtrack*): "On se voit
  mardi, non, plutôt mercredi" is written "On se voit mercredi.", "Let's meet at 2,
  actually 3" is written "Let's meet at 3." Local rules (`backtrack.py`), French and
  English, no language model; `corrections = false` in `[model]` turns them off.
- `bench/backtrack/`: a reproducible measure — 30 corrections and 16 control sentences,
  their expected text and synthetic recordings. Word error rate against the expected
  text, before → after:
  - written sentences: 81.3 % → 6.0 %, 28/30 exact; controls 0 % → 0 %;
  - faster-whisper `small` (CPU, int8): 86.7 % → 18.7 %, 17/30 exact; controls
    2.7 % → 2.7 % (transcription slips, left as they were);
  - faster-whisper `large-v3-turbo` (CUDA, float16): 86.0 % → 20.7 %, 19/30 exact;
    controls untouched.
  What remains is mostly the transcription itself ("14h" for "14 heures", "Mais le titre"
  for "Mets le titre"), not the corrections.
- `docs/wispr-flow-gap.md`: the features and qualities of Wispr Flow, and where
  whisper-desk stands on each.

### Changed

- The repository moved to `hermez-agency/whisper-desk`: the installation command, the
  README and the site point there. `whisper-desk update` on an installation made before
  the move reads the new home instead of `SalvadorCardona/whisper-desk`, and `install.sh`
  writes the new name in the fingerprint, even when called with the old one.
- **Developer syntax** (Wispr Flow writes variable names in their style): say the style,
  then the name — *camel case user name* is written `userName`, *pascal case payment
  service* `PaymentService`, *snake case created at* `created_at`, *kebab case* (or *dash
  case*) *user profile* `user-profile`, *constant case* (or *screaming snake case*) *max
  retries* `MAX_RETRIES`. The name runs until the sentence goes on: a mark, a word such as
  *et*, *dans*, *est*, *and*, *from*, *to*, *is*, or another style; *by* and *at* belong to
  it (`getUserById`, `created_at`). The forms Whisper writes are understood — apart
  (*Camel Case User ID*), glued (*camelCaseUserName*, *SnakeCaseParseDate*) or hyphenated
  (*constant-case-database-url*). The style named without a name after it (*on écrit en
  snake case*, *we use camel case for variables*) or after an article (*a constant case of
  bad luck*, *un kebab, case départ*) stays as words. Local rules (`casing.py`), applied
  after the spoken punctuation; `developer_syntax = false` in `[model]` keeps the words.
- `bench/casing/`: 24 sentences that say a name in a style and 12 control sentences, with
  synthetic recordings. Names written exactly as expected, before → after:
  - written sentences: 0/25 → 25/25, 24/24 sentences exact; controls unchanged;
  - faster-whisper `small` (CPU, int8): English 0/12 → 5/12; controls unchanged;
  - faster-whisper `large-v3-turbo` (CUDA, float16): English 0/12 → 7/12; controls
    unchanged.
  What remains is the transcription: Whisper mishears the words of the name (*use of
  settings* for *user settings*, *orth provider* for *auth provider*). The French
  recordings are no measure: the French synthetic voice cannot say English words, and
  Whisper hears none of the 13 names in them, before or after.
