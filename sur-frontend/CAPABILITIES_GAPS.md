# Backend fields the frontend needs

Per the rule "if a task requires a backend field that doesn't exist yet, list
it rather than inventing a client-side workaround". Split into what I added
while doing this work, and what is still genuinely missing.

## Added during this change (previously absent)

These did not exist and were blocking tasks, so they were added to the backend
rather than faked client-side.

| Field | Where | Why the UI needed it |
|---|---|---|
| `GET /api/capabilities` | new endpoint | Nothing published the supported languages or emotions at all. |
| `languages[].display_name`, `.tts_available` | capabilities | Render the picker and mark translate-only entries. |
| `emotions[].label`, `.color` | capabilities | Render only real labels, with colour decided once server-side. |
| `emotion_confidence_floor` | capabilities | The "uncertain" threshold is one number in one place, not a frontend constant. |
| `segment.detected_language` | `segments` | Show what ASR actually detected (Task 3). |
| `segment.detected_language_confidence` | `segments` | Show detection confidence. |
| `project.source_language` | `projects` | The confirmed/corrected source language. |
| `project.review_language` | `projects` | Whether the run pauses for confirmation. |
| `project.status = awaiting_language_confirmation` | `projects` | The gate state the UI renders the confirm panel for. |
| `POST /api/projects/{id}/confirm-language` | new endpoint | Accept or correct the detection and resume (Task 3). |
| `project.error_is_permanent` | `projects` | Say "Retrying…" only when a retry can help (Task 7). |
| WS `stage_progress.completed` / `.total` | events | "TTS 4/17" instead of a bare percentage (Task 6). |
| WS `error.permanent` | events | Same distinction, live. |

## Resolved since the list above (2026-09-10, the 5-screen rewrite)

- **Gap #1 below (`source_languages` missing) is now fixed.**
  `/api/capabilities` now returns `source_languages: [{code, display_name}]`,
  derived from `app/capabilities.SOURCE_LANGUAGES` (English + every Indic
  language IndicTrans2 has an indic->en/indic->indic path for).
  `DetectedLanguageGate`'s override `<select>` reads this list, not the
  target `languages` list. Left in the table above for history.
- Also added this pass, all real and enforced server-side (not decorative):
  `languages[].flores_code`, `emotions[].index`, `asr_autodetect`, `device`,
  `max_upload_mb`, `accepted_formats` (with real content-type and size
  enforcement in `routes_projects.py`/`routes_storage.py`, not just
  reported).

## Still missing — the UI works around these, and shouldn't have to

1. ~~`GET /api/capabilities` does not report source languages for ASR.~~ Fixed
   above.

2. **No per-project ETA or throughput from the backend.**
   The ETA shown is measured client-side from observed `stage_progress`
   timings. That is honest but resets on reconnect and can't account for
   queue depth. **Needed:** either `stage_progress.eta_seconds`, or enough
   for the client to compute one that survives a reload
   (`stage_started_at` per stage).

3. **`tts_available` is currently `true` for every language.**
   It is wired end to end and the UI honours it, but the backend sets it from
   a hardcoded default on `Language` rather than asking the TTS provider what
   voices it actually has. **Needed:** derive it from the configured TTS
   provider, the same way emotion labels are derived from the model. Until
   then "translate only" will never appear in production even if it should.

4. **No `GET /api/projects/{id}/events` replay.**
   Progress is only available over the WebSocket. A reload mid-run shows an
   empty stage list until the next event arrives; the UI polls the project to
   compensate, which gives status but not per-stage counts. **Needed:** last
   known stage state on the project resource.

5. ~~Cancel is not implemented~~ Removed instead: the 5-screen rewrite has no
   Cancel button anywhere. It was a no-op inherited from the original
   Figma-Make design; rather than wire a fake control to a real backend gap,
   it was dropped. `POST /api/projects/{id}/cancel` is still a real gap if a
   working Cancel is wanted later.

6. **No way to pre-select a known, non-autodetected source language before
   ASR runs.** `ProjectCreate`/`ProcessRequest` have no `source_language`
   field -- the only place `project.source_language` can be set is
   `POST /confirm-language`, which only applies *after* ASR has already run
   and the project is `awaiting_language_confirmation`. So the New Dubbing
   modal's "Language of the source" step cannot offer "I already know it's
   Hindi, skip detection" -- it can only show whether this deployment
   autodetects at all (`asr_autodetect`) and let the user choose whether to
   pause for confirmation afterward (`review_language`). **Needed:** a
   `source_language_hint` (or similar) field on `ProcessRequest` that, when
   set, pins the ASR call for that project instead of using the
   deployment-wide `ASR_LANGUAGE` setting.

7. **No toggle for "preserve original pauses and timing."** There is only
   one mux behavior today: `ffmpeg_utils.mux_timeline()` always places every
   clip at its source segment's absolute timecode. The old back-to-back
   concatenation this checkbox would have disabled was removed earlier this
   project specifically because it caused the sync-drift bug the
   `test_output_duration_matches_source_video`-style tests now guard
   against. Rendering the checkbox anyway would be a control with no
   backend effect, so the New Dubbing modal omits it and exposes the three
   options that are real (`preserve_emotion`, `clone_voice`,
   `lip_sync_aware`) instead. **Needed, if a real "pack clips tighter, drift
   more" mode is ever wanted:** a `ProcessRequest.preserve_timing: bool`
   field and a second mux code path.

8. **No live "model load state."** `/api/capabilities`'s `providers` field
   reports the *configured* mode (`mock`/`real`) per stage, not whether a
   worker currently has that model's weights loaded in memory. The
   fail-loud startup check (`app/startup_checks.py`) runs once at worker
   boot and either lets the process start or kills it -- it doesn't persist
   a result anywhere queryable. The Runtime screen shows configured mode
   only and says so. **Needed:** something like a Redis key each worker
   sets after its own self-check, and an endpoint that reads it.
