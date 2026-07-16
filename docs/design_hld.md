# Design High-Level Design (HLD)

**Project:** Presence-Aware Social Robot with Watch-Mediated Consent
**Type:** MSc thesis prototype
**Companion document:** [Technical HLD](technical_hld.md) — the *how* (architecture,
interfaces, concurrency, technology). This document is the *why*: problem, goals, the
privacy/consent model, interaction design, key decisions and their trade-offs, the threat
model, and the GDPR mapping.

For a source-level map of the current checkout, including scheduled reminders and known
runtime deviations, see the [Codebase Guide](codebase_guide.md).

---

## 1. Purpose and audience

This document captures the **design intent** of the system — the requirements it answers,
the principles it commits to, the decisions taken and rejected, and the privacy reasoning
that makes those decisions defensible. It is written for thesis assessment and for anyone
extending the prototype; implementation specifics are cross-referenced to the Technical HLD
rather than repeated.

---

## 2. Problem statement and motivation

Social and assistive robots increasingly speak **scheduled personal content** aloud — for
example a **reminder** the owner set for themselves ahead of time ("don't forget your
doctor's appointment at four"). Spoken aloud, a reminder about a medical appointment, a
payment, or a private arrangement is a **disclosure of health-adjacent or otherwise
special-category personal data** — and robots are typically used in *shared* spaces where
**bystanders** are present.

> **Core tension:** the moment a reminder is most useful (it has just come due) is often
> the moment it is most sensitive (other people are in the room). A naïve robot that simply
> speaks the reminder discloses its content to whoever is nearby, with no consent and no
> memory of who already knows.

**Thesis goal.** Build and evaluate a robot that treats disclosure-in-front-of-others as a
consent decision that (a) is made **privately** by the data subject in the moment, (b) is
**remembered per bystander** so it is not repeatedly re-asked, and (c) **fails safe**
(withholds) whenever consent is absent, late, or uncertain. The design target is a
**GDPR-flavoured privacy model**: no sensitive content surfaces in front of a third party
without an explicit, in-the-moment, *private* "yes" from the data subject — given on the
watch, never spoken aloud or typed on the laptop.

---

## 3. Goals and non-goals

**Goals**

- G1 — Disclose a **sensitive reminder** in front of a bystander **only** on explicit,
  private, in-the-moment consent.
- G2 — **Remember** each bystander's decision and never re-ask about the same person
  (the "cache-memory" policy).
- G3 — **Fail safe**: absence/uncertainty of consent ⇒ withhold, and never record a
  non-decision as a preference.
- G4 — Give consent through a **private channel** (the wrist), decoupled from the public
  channel (the robot's voice) and from the operator laptop.
- G5 — Support **two sensing modalities** (camera, microphone) over one shared consent core.
- G6 — Be **deployable on a commodity laptop** in real time while holding both device links.
- G7 — Provide an **empirical justification** for the sensing-algorithm choices.
- G8 — **Classify each reminder locally** as sensitive or non-sensitive, and route only the
  sensitive ones through the private consent channel.

**Non-goals**

- Not a medical device; a due reminder is scheduled content the owner authored, not a
  physiological reading or a diagnosis.
- Not multi-user consent arbitration (one owner/data-subject per session).
- Not cloud/remote processing — all sensing and identity stay on the laptop.
- Not hardened security (research prototype; BLE pairing/auth is out of scope, see §11).
- Not robust face/speaker recognition at scale — identities are local, per-session-ish.
- Not a guaranteed-delivery reminder service; the scheduler is an at-most-once research
  prototype using the laptop's local clock.

---

## 4. Design principles

| # | Principle | Manifestation |
| --- | --- | --- |
| P1 | **Privacy by design & by default** | The default action is *withhold*; disclosure is the exception that requires an affirmative private act. |
| P2 | **Private channel for private decisions** | Consent is a wrist buzz + Yes/No, never spoken by the robot or typed on the laptop. |
| P3 | **Consent is a first-class, durable object** | A `(bystander set) → YES/NO` record persists across restarts; it can be inspected and deleted. |
| P4 | **Safe by omission** | Timeouts, dropped links, and unreachable watches all resolve to withhold — and are *not* cached. |
| P5 | **Data minimisation** | Identity stores keep embeddings rather than raw images/audio; reminders additionally persist only confirmed text, due time, a sensitivity label, and delivery state. |
| P6 | **Local-only processing** | Camera/mic frames, embeddings, and decisions never leave the laptop. |
| P7 | **Modality-agnostic core** | One owner-vs-bystander + consent-memory design serves both camera and voice. |
| P8 | **Deployability as a hard constraint** | Algorithm choices are judged on latency/memory/friction, not just accuracy (§12). |

---

## 5. Requirements

### 5.1 Functional requirements

| ID | Requirement |
| --- | --- |
| FR1 | Capture a private reminder by voice and store it locally with a parsed due time and a **sensitivity label**. |
| FR2 | Treat a reminder becoming **due** as the arming condition; hold a due reminder until the watch is in range. |
| FR3 | Sense whether a bystander is present (camera: a face in view; voice: a non-owner speaking). |
| FR4 | Distinguish the **owner** (watch-wearer) from **bystanders**. |
| FR5 | When a **sensitive** reminder is due **and** a bystander is present **and** the watch is connected, request consent **on the watch** (buzz + Yes/No). |
| FR6 | On **Yes**, have the robot speak the reminder; on **No** (or no reply), stay neutral and deliver the reminder privately to the wrist. |
| FR7 | **Remember** the decision keyed by bystander and reuse it without re-asking (cache-memory policy). |
| FR8 | Provide a **baseline** policy that always re-asks and never remembers (control condition). |
| FR9 | Withhold (and not cache) whenever consent is absent, late, or the link drops. |
| FR10 | Enroll the owner once per modality; identities and decisions persist across runs. |
| FR11 | Deliver a **non-sensitive** reminder immediately (no presence check, no consent), and speak a sensitive reminder outright when the owner is alone. |

### 5.2 Non-functional requirements

| ID | Requirement | Target / rationale |
| --- | --- | --- |
| NFR1 | **Real-time responsiveness** | The preview loop stays interactive; blocking work runs off the UI thread. |
| NFR2 | **Co-located device budget** | One laptop process holds BLE + USB serial concurrently (the binding constraint). |
| NFR3 | **Deployability / low friction** | CPU-only, pip-installable, no compile step (dlib deliberately avoided). |
| NFR4 | **Privacy-safe failure** | Every ambiguous outcome degrades to withhold. |
| NFR5 | **Persistence & durability** | Atomic writes; memory survives crashes/restarts. |
| NFR6 | **Portability** | macOS + Linux (BLE via bleak; TTS via espeak/`say`). |
| NFR7 | **Auditability** | Consent records are a small, human-readable, deletable JSON file. |

---

## 6. The consent & privacy model (core design)

The system's identity is this decision pipeline. Every modality and policy funnels through
it.

```mermaid
flowchart TD
  A["Reminder becomes due"] --> W{Watch connected?<br/>(owner in room)}
  W -- no --> Hold["Hold reminder<br/>· wait for the owner"]
  W -- yes --> S{Sensitive<br/>reminder?}
  S -- no --> Speak["Robot SPEAKS the reminder<br/>(no presence check)"]
  S -- yes --> P{Bystander present?<br/>(camera face / non-owner voice)}
  P -- "no · owner alone" --> Speak
  P -- yes --> ID["Identify bystanders<br/>(subtract the owner)"]
  ID --> K["Build key =<br/>sorted set of bystander IDs"]
  K --> M{Remembered<br/>decision?}
  M -- "YES" --> D["Robot SPEAKS the reminder<br/>(no prompt)"]
  M -- "NO" --> H["Deliver to wrist privately<br/>· neutral greeting"]
  M -- "miss" --> ASK["Ask watch privately<br/>(buzz + Yes/No)"]
  ASK -- "Yes" --> Dp["Store YES → SPEAK"]
  ASK -- "No" --> Hp["Store NO → wrist + neutral"]
  ASK -- "no answer / drop" --> Safe["To wrist · neutral<br/>(do NOT store)"]
```

**The trigger is a reminder becoming due.** Reminders are captured ahead of time by voice,
parsed for a due time, and classified locally as sensitive or non-sensitive (§9). Every due
reminder is first *held* until the BLE link confirms the owner is in the room. Once the owner
is present, a **non-sensitive** reminder is simply spoken; a **sensitive** reminder is then
presence-gated — spoken outright if the owner is alone, and put to the per-bystander consent
decision only when a bystander is also sensed. Both sensing modalities (camera and voice)
share this one decision path.

**Three ideas do the privacy work:**

1. **The watch is a private disclosure channel.** The consent question is delivered to the
   *wrist* (a buzz and an on-screen Yes/No), not spoken by the robot. The bystander neither
   hears the question nor sees the answer. The public channel (robot speech) and the private
   channel (watch) are physically separate devices.

2. **Owner presence is established by BLE, not by the sensor.** As long as the watch holds a
   BLE link (≈ 10 m ≈ "same room"), the owner is taken to be present — *even if not on
   camera or not the one talking*. The camera/mic is then used only to detect and identify
   **bystanders**; the enrolled owner template is *subtracted* from what is seen/heard. This
   cleanly separates "the data subject is here" from "who else is here", and it is what lets
   a trial fire when only a bystander is visible.

3. **Consent is remembered per bystander, and only real decisions are remembered.** A Yes/No
   is cached against the specific bystander ID(s) so the same person is never re-asked; but a
   *non-answer* (timeout / dropped link) is explicitly **not** cached, because absence of a
   decision is not a preference.

---

## 7. Interaction and UX design

**Principle: the laptop terminal never takes a decision.** The only laptop input in a live
session is pressing `q` in the preview window. Every consent decision is a wrist tap. This
keeps the sensitive act on the data subject's own private device.

| Touchpoint | Channel | Design |
| --- | --- | --- |
| Consent request | **Watch** (buzz 400 ms + modal) | *"I have noticed that someone is present with you. Do you want me to send private reminders in front of them?"* — Yes/No, titled "Robot asks". |
| Consent **Yes** / owner alone / non-sensitive | **Ohbot** (spoken) | *"Here is your reminder. `<text>`."* — the reminder is read aloud on the public channel. |
| Consent **No** / no reply | **Ohbot** (spoken, neutral) **+ Watch** (private note) | Ohbot says *"Hello there."* while the reminder is pushed privately to the wrist via `notify(...)` as *"Reminder: `<text>`"*, so the bystander notices nothing unusual. |
| Operator status | Laptop HUD overlay | Face count, watch link (OK/OFFLINE), next reminder due, last-delivery result. |
| Enrollment | Camera/mic window + one `yes` keystroke to overwrite | Sit/speak alone; a live "OWNER / other" check confirms the template discriminates you. |

**Design intent of the "No → Hello there."** The withhold response is deliberately a
plausible, neutral greeting rather than silence, so that declining disclosure does not
itself signal to the bystander that something private was suppressed. The reminder is not
lost — it is delivered privately to the wrist — so privacy is preserved *both* by keeping
the content off the public channel *and* by not drawing attention to the withholding.

---

## 8. Two consent policies (experimental design)

Consent memory is the experiment's independent variable, crossed with the two sensing
modalities (§9) to give a **2×2 of four runnable apps**. Within each modality a
**cache-memory** app (remembers the bystander's Yes/No and reuses it) and a **re-consent
baseline** app (re-asks every time, stores nothing) share an **identical sensing and
recognition pipeline** and differ **only** in how consent memory is handled — a clean
experimental pair, and the *same* remember-vs-reask contrast in both the camera and the mic
modality:

| | **Cache-Memory** — remembers (`robot/apps/camera_remember.py`, `robot/apps/mic_remember.py`) | **Re-Consent baseline** — re-asks (`robot/apps/camera_reask.py`, `robot/apps/mic_reask.py`) |
| --- | --- | --- |
| First encounter with a bystander | Ask on the watch | Ask on the watch |
| Subsequent encounters (same person) | **Reuse** the stored answer, no prompt | **Ask again every time** |
| What is persisted | The Yes/No decision (per-modality `consent_cache*.json`) | **Nothing** about decisions |
| Recognition still runs? | Yes (owner filtered, bystander IDs minted) | Yes (identical) — but used only for logging |
| Role in the thesis | The proposed policy | The privacy/UX **control condition** |

Because the only removed element is the `ConsentStore` lookup, **any measured behavioural
difference is attributable to consent memory, not to sensing** — the intended
independent-variable isolation. The design question each pair answers: *does remembering
per-bystander consent improve the interaction (fewer interruptions) without weakening the
privacy guarantee?*

---

## 9. Two sensing modalities (camera & voice)

"Is a bystander present, and who are they?" is answered two ways, feeding the **same**
downstream logic.

| | **Camera** | **Voice** |
| --- | --- | --- |
| Presence cue | A face in view | Someone (non-owner) speaking |
| Identity model | YuNet detect + **SFace** 128-D embedding | **Resemblyzer** GE2E 256-D d-vector |
| Owner enrollment | `robot/apps/enroll_face.py` | `robot/apps/enroll_voice.py` |
| Independent state | `owner_face.json`, `face_db.json`, `consent_cache.json` | `owner_voice.json`, `voice_db.json`, `consent_cache_voice.json` |

**Shared, not duplicated.** Both modalities reuse the *same* `FaceDB` (gallery) and
`OwnerStore` (owner template) classes — they are embedding-agnostic, so the voice pipeline
just points them at different files with different thresholds. The owner-vs-bystander story
is therefore identical across audio and video, by construction.

**A third embedding, same family.** Reminder *sensitivity* is decided the same way presence
identity is: a local sentence-transformer (`all-MiniLM-L6-v2`) embeds the reminder text and
compares it by cosine similarity to small labelled prototype sets (sensitive vs everyday),
backed by a high-precision keyword override for explicit medical/financial terms. It runs
entirely offline and, on a near-tie, defaults to *sensitive* (privacy-safe); if
`sentence-transformers` is unavailable it falls back to a keyword heuristic. Owner-vs-bystander
(face, voice) and sensitive-vs-everyday (text) are thus one embedding-and-cosine idea applied
to three signals.

**Inherent limit (accepted by design):** voice can only notice a bystander who *speaks*. A
silently-present third party is invisible to the microphone — which is exactly the case the
camera covers. The two modalities are complementary rather than redundant. (Owner presence
is BLE-driven in both, so the owner need not be the one talking / on camera.)

**Threshold trade-offs are modality-specific:**

| | Camera | Voice |
| --- | --- | --- |
| Same-person (gallery) | 0.363 | 0.70 |
| Owner match | 0.50 (**well above** same-person) | 0.73 (**just above** same-speaker) |
| Worst error to avoid | *False* owner match → corrupts the cache key | *Missed* owner window → misfiled as bystander → spurious prompt |

For faces, a false-positive owner match is the expensive error, so the owner bar is raised
**well above** the same-person bar (0.50 vs 0.363). For voice, a *missed* owner window is the
expensive error, so the owner bar sits **just above** the same-speaker bar (0.73 vs 0.70)
rather than far above it, so the owner is rarely misfiled as a bystander. Same principle —
protect the cache key and avoid spurious prompts — with the owner-bar gap tuned to each
modality's dominant error. (Absolute values differ because SFace cosines run lower than
Resemblyzer d-vector cosines.)

---

## 10. Key design decisions and trade-offs

| ID | Decision | Rationale | Trade-off accepted |
| --- | --- | --- | --- |
| DD1 | **Consent on the watch**, never spoken or typed | Keeps the sensitive act on the data subject's private device (P2) | Requires the wearer to notice/act on a wrist prompt |
| DD2 | **BLE link = owner presence** | Decouples "owner is here" from "who else is here"; lets trials fire with only a bystander visible | BLE range (~10 m) is a coarse proxy for "same room" |
| DD3 | **Withhold on no-answer, and don't cache it** | A non-decision is not a preference (P4) | The wearer may need to answer again next time if they never tapped |
| DD4 | **Remember per-bystander** (cache-memory) | Avoids nagging; treats consent as durable | Stored decisions can go stale if a relationship/context changes (mitigated: file is deletable) |
| DD5 | **Cache key = sorted set of bystander IDs** | A group of the same people maps to one stable decision | A new person in the group is a new key ⇒ re-ask (intended) |
| DD6 | **Blocking work off the UI thread** | Keeps the preview responsive (NFR1); avoids frozen-window kills | Concurrency complexity (locks, single-slot trial) |
| DD7 | **Two policies sharing one pipeline** | Clean experimental isolation of the memory variable | Some duplicated main-loop code between scripts |
| DD8 | **Embedding-agnostic recognition core** | One design serves both modalities (P7) | `_cosine` duplicated; no shared utils module yet |
| DD9 | **espeak TTS + `NO_OHBOT` OS-voice fallback** | Develop/demo without the robot; portable | espeak voice quality is modest |
| DD10 | **Deployability-first algorithm selection** | The real constraint is CPU real-time with both links held (NFR2/3) | Not the most accurate models available (ArcFace/ECAPA are the ceiling, not the choice) |
| DD11 | **Local-only, minimal storage** (embedding + Yes/No) | Data minimisation & purpose limitation (P5/P6) | No cross-device sync; identities don't generalise beyond this laptop |
| DD12 | **Classify reminder sensitivity locally, default-sensitive on a tie** | Non-sensitive reminders need no gate; sensitive ones must never slip through; offline keeps the text on the laptop (P6) | A borderline everyday reminder may be gated as sensitive (accepted — privacy-safe) |

---

## 11. Threat model & privacy analysis

**Primary asset:** the wearer's private reminders and their disclosure decisions.
**Adversary of concern:** an *incidental bystander* who could overhear sensitive content
they were never authorised to hear. (This is a **privacy** design, not a security-hardened
system — see the out-of-scope note.)

| Threat | Mitigation (by design) |
| --- | --- |
| Sensitive content spoken in front of a non-consented bystander | Disclosure gated on an affirmative private Yes; default is withhold (P1/P4) |
| Consent question itself leaking that a private reminder is pending | Question delivered to the wrist (buzz + screen), not spoken aloud (DD1) |
| A dropped link mid-prompt silently recorded as "No" | BLE cancel is distinguished from a real No; non-answers are never cached (DD3) |
| Withholding *itself* signalling suppression to a bystander | The withhold response is a natural neutral greeting, not conspicuous silence (§7) |
| Over-collection of bystander data | Only an embedding + a Yes/No are stored for identity/consent — no raw frames, audio, or names (P5) |
| Data exfiltration | All processing and storage are local to the laptop (P6) |
| Stale/unwanted memory | Consent + gallery files are small, human-readable, and deletable (P3, NFR7) |
| Sensitive reminder text retained or committed | Reminder text/time is local, deletable, and gitignored under `robot/state/` (never committed); it is retained on disk until the owner clears it. |

**Residual risks / accepted limitations:** BLE is unauthenticated (an attacker in range
could in principle inject `consent(...)` or spoof `CONSENT:` replies — out of scope for the
prototype); owner-vs-bystander depends on enrollment quality; a bystander mis-identified as
a *new* person triggers a fresh (correct-by-default) prompt; the sensitivity classifier can
mislabel an atypically-worded reminder; a silent bystander is invisible to voice reminder
delivery. See
[Technical HLD §11](technical_hld.md#11-known-limitations--technical-debt).

---

## 12. GDPR / data-protection mapping

The design is explicitly shaped by GDPR principles (framing, not a compliance claim):

| GDPR principle | How the design addresses it |
| --- | --- |
| **Lawfulness — consent** (Art. 6/9; health is special-category, Art. 9) | Disclosure requires an explicit, freely-given, in-the-moment affirmative act by the data subject on their own device. |
| **Purpose limitation** (Art. 5(1)(b)) | Consent authorises one thing — speaking a **sensitive** reminder in front of a specific bystander; non-sensitive content bypasses the store entirely and a stored Yes/No is scoped to the bystander it was given for. |
| **Data minimisation** (Art. 5(1)(c)) | Identity/consent stores contain an embedding + Yes/No rather than raw media or names; reminder storage is limited to confirmed text, due time, ID, a sensitivity label, and delivery state. |
| **Storage limitation** (Art. 5(1)(e)) | State is local, tiny, and user-deletable; the baseline policy stores nothing at all. |
| **Integrity & confidentiality** (Art. 5(1)(f)) | Local-only processing; atomic writes; private consent channel. |
| **Data subject in control** (Arts. 7, 17) | Consent is per-person and revocable by deleting the cache; enrollment is re-runnable. |
| **Privacy by design & default** (Art. 25) | Withhold-by-default; disclosure is the deliberate exception (P1). |

---

## 13. Future design directions

Driven by the evaluation workstream ([`docs/algorithm_comparison.md`](algorithm_comparison.md)) and open design questions:

- **Drop Haar for the cheap presence count** — the benchmark shows Haar is the *slowest*
  detector; YuNet alone can serve both the per-frame count and precise boxes with no latency
  penalty and one fewer moving part.
- **Upgrade VAD** — WebRTC VAD is a near-zero-cost robustness win over the RMS energy gate
  (already an installed dependency); Silero is the accuracy ceiling to validate.
- **Evaluate x-vector for speaker ID** — it is *faster* than the shipped Resemblyzer GE2E
  and a candidate upgrade pending the EER comparison.
- **Record the labelled eval set** to turn the pending accuracy/EER columns into numbers
  (`capture_eval_set.py`, ~10 min), keeping ArcFace/ECAPA as reported accuracy ceilings, not
  deployment candidates.
- **Evaluate the sensitivity classifier** — measure how reliably the local sentence-transformer
  plus keyword override separates sensitive from everyday reminders, and study the
  default-sensitive tie-break as a privacy/utility trade-off.
- **Design questions for the thesis** — a richer sensitivity taxonomy (beyond a single
  sensitive/non-sensitive split); consent expiry/decay; multi-party arbitration; sensor
  fusion (camera + voice together); BLE authentication for a non-prototype deployment.

---

## 14. Design ↔ requirements traceability

| Requirement | Realised by (design element) |
| --- | --- |
| FR1–FR2 | Voice reminder capture (`robot/apps/add_reminder.py`: Whisper + dateparser + local sensitivity classifier → `reminders.json`); due-time arming held on the BLE link (voice apps `robot/apps/mic_remember.py` and `robot/apps/mic_reask.py`, thin wrappers over the shared `robot/core/voice_reminder.py` engine; camera demos poll the store) |
| FR3–FR4 | Presence vote + owner-subtraction (BLE presence + embedding template) |
| FR5–FR6 | Watch consent channel + Ohbot disclose/withhold behaviours |
| FR7 | Per-bystander `ConsentStore` (cache-memory policy) |
| FR8 | Re-consent baselines `robot/apps/camera_reask.py` and `robot/apps/mic_reask.py` (always re-ask, never remember) — one per modality |
| FR9 | Safe-default withhold, non-answers uncached |
| FR10 | `robot/apps/enroll_*.py` + persistent JSON state |
| FR11 | Local sensitivity classifier → non-sensitive and owner-alone short-circuits in the shared delivery policy |
| NFR1–NFR2 | Off-thread trial worker; single co-located host process |
| NFR3, NFR7 | CPU-only pip stack; small deletable JSON state |
| NFR4–NFR5 | Withhold-on-uncertainty; atomic writes |

*See the [Technical HLD](technical_hld.md) for the architecture, interface/protocol
specifications, concurrency model, and technology stack that implement this design.*
