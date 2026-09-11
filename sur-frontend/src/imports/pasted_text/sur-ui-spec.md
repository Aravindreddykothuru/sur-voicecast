For the **Sur — AI Emotion-Aware Dubbing Engine**, the UI should not look like a normal marketing website. The PRD explicitly describes it as a **dark, technical “studio” interface** focused on reviewing and editing dubbed video/audio. 

### UI should have these 6 main screens

| Screen                    | What should be present                                                                                          |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **1. Dashboard**          | Project cards, project name, processing status/stage, target language, video duration                           |
| **2. New Project**        | Video upload, target-language selection, feature toggles: **Voice Clone, Emotion Preservation, Lip-Sync**       |
| **3. Processing Tracker** | Overall progress, individual pipeline stages, live processing log, Cancel/Retry                                 |
| **4. Segment Editor** ⭐   | Waveform/timeline, source English text, translated text editor, emotion badge, audio preview, regenerate button |
| **5. Preview & Compare**  | Original video/audio vs dubbed version, synchronized playback, segment-level sync offset                        |
| **6. Export**             | Format/resolution selection, QA report, quality metrics, final export/download                                  |

These six screens and their key components are directly specified in the PRD. 

### The most important screen: Segment Editor

This is the **core UI**. Don't waste most of your design effort on the dashboard.

It should look roughly like:

```text
┌──────────────────────────────────────────────────────────┐
│ SUR                         Project: Movie_01     Export │
├───────────────┬──────────────────────────────────────────┤
│ SEGMENTS      │              VIDEO PREVIEW               │
│               │                                          │
│ 00:00  S1     │          ┌──────────────────┐            │
│ 00:04  S2  ←  │          │                  │            │
│ 00:09  S3     │          │      VIDEO       │            │
│ 00:15  S4     │          │                  │            │
│               │          └──────────────────┘            │
├───────────────┴──────────────────────────────────────────┤
│  WAVEFORM                                                │
│  ────────████████───████──────████████────────          │
│       00:04       00:08       00:12                     │
├──────────────────────────────────────────────────────────┤
│ SOURCE                                                   │
│ "What are you doing here?"                              │
│                                                          │
│ TRANSLATION                                              │
│ [ Telugu translated sentence......................... ] │
│                                                          │
│ Emotion: [ 😠 ANGRY ]   Intensity: ███████░░ 78%        │
│                                                          │
│ ▶ Play Dub       🔄 Regenerate Segment                   │
└──────────────────────────────────────────────────────────┘
```

The PRD specifically requires a **wavesurfer.js waveform with emotion-colored regions, editable translation, emotion editing, segment regeneration, and inline TTS playback**. 

### Important UI elements

**1. Emotion system**

Use consistent emotion badges for:

* 😠 Anger
* 😊 Happiness/Joy
* 😢 Sadness
* 😨 Fear
* 😲 Surprise
* 😐 Neutral

The same emotion labels/colors should appear in both the **Segment Editor and Preview screen**. 

**2. Timecode & status**

Use a **monospace font** for:

* `00:01:24.520`
* Duration
* Sync offset
* Processing status
* Segment timestamps

The PRD explicitly calls for monospace typography for timecodes, durations and status badges. 

**3. Processing stages**

Show something like:

```text
✓ Upload
✓ Audio Extraction
✓ Speech Recognition
✓ Translation
● Voice Synthesis       72%
○ Mux & Export
```

The backend sends real-time stage events such as `stage_started`, `stage_progress`, `stage_completed`, `segment_ready`, and `error`, so the UI should reflect those states. 

**4. Preview & comparison**

You need:

```text
ORIGINAL                    DUBBED
┌──────────────┐            ┌──────────────┐
│    VIDEO     │            │    VIDEO     │
└──────────────┘            └──────────────┘

        ▶ Play / Pause

Segment 12
Original:  3.20 sec
Dubbed:    3.35 sec
Sync:      +4.7% ✓
```

The PRD requires synchronized original/dubbed playback and a per-segment sync-offset indicator. 

### Export screen

Show a QA-oriented result rather than just a giant **Download** button:

```text
EXPORT PROJECT

Format       [ MP4 ▼ ]
Resolution   [ 1080p ▼ ]

QUALITY REPORT
────────────────────────────────
Segment       WER    Sync     Speaker
S001          3.2%   +2.1%    94%
S002          4.1%   -1.4%    91%
S003          2.8%   +3.0%    96%
────────────────────────────────

             [ EXPORT VIDEO ]
```

The required QA report includes **WER, sync offset and speaker-similarity score per segment**. 

### Overall visual style

Go with:

* **Dark background**
* Clean studio/editor layout
* Sans-serif for normal text
* Monospace for technical data
* Consistent emotion indicators
* Clear green/neutral/error states
* Minimal unnecessary decoration
* Strong timeline/waveform focus
* Responsive editor down to **768px**
* Keyboard navigation between segments
* ARIA labels for custom player controls
* Proper loading/error states

Those accessibility and responsive requirements are explicitly included in the frontend specification. 

**Bottom line:** Design it like **Adobe Premiere/Audition + an AI dubbing editor**, not like a generic SaaS dashboard. The **Segment Editor + Processing Tracker + Preview/Compare** are the parts that will make or break the UI.
