"""AI sensitivity classifier for reminders.

Decides whether a reminder's text is *sensitive* - private health / financial /
personal content that should be gated behind presence + watch consent before
being spoken aloud - or *non-sensitive*, an everyday errand that is safe to
speak normally even with a bystander around:

    "Doctor's appointment tomorrow"  -> sensitive   (ask consent if others near)
    "Take medication at 8 PM"         -> sensitive
    "Buy milk"                        -> non-sensitive (just say it)
    "Water the plants"                -> non-sensitive

This mirrors the thesis's core method rather than bolting on something foreign:
the voice and face pipelines turn a signal into a neural embedding and compare
by cosine similarity (Resemblyzer d-vectors, SFace). Here we do exactly that for
*text* - a sentence-transformer encodes the reminder, and we compare it (cosine)
against small, labelled sets of example reminders ("prototypes") for each class.
The class whose examples are most similar wins.

Crucially the classifier is LOCAL: no cloud call, no API key, the reminder text
never leaves the device - which matters, because sending private reminders to a
remote service to decide if they are private would defeat the point of the
watch-mediated privacy design.

If sentence-transformers is not installed (or its model can't load offline on a
first run), a transparent keyword fallback keeps the demo running; it prints
that it is in fallback mode so the degraded accuracy is never silent.

Decision (a *specificity* rule): a reminder is sensitive only if it is genuinely
similar to some sensitive example - not merely "closer to sensitive than to
everyday". Real medical/financial reminders sit at cosine 0.6-1.0 against the
sensitive prototypes, so they gate reliably; a meaningless phrase that resembles
nothing ("reminder after 2 minutes", ~0.3) is spoken freely instead of being
flagged. On a genuine near-tie that still clears the bar we keep it sensitive -
the privacy-safe side of a coin-flip - because a needless consent tap for an
errand is cheap, while speaking "doctor's appointment" aloud in front of a
bystander is the harm the whole system exists to prevent. Tune the bar with
``SENSITIVE_ABS_SIM``; the owner can also flip any label at add time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# The sentence-transformer to embed reminder text. ~80 MB, downloads to the
# HuggingFace cache on first use, then runs offline on CPU in a few ms.
MODEL_NAME = "all-MiniLM-L6-v2"

# Labelled prototypes. Classification is nearest-neighbour by cosine: a reminder
# is scored by its single closest example in each class. Add real-world phrasings
# here to tune - no retraining, the embeddings update automatically.
#
# Keep the SENSITIVE examples focused on the sensitive *topic* itself and free of
# incidental everyday words (times, meals, days). An earlier example ended in
# "...pills after lunch", which made an unrelated "Lunch after one minute" match
# it at 0.53 on the shared word "lunch" - a false positive. Phrase each example
# so its embedding keys on what makes it private, not on scheduling words.
SENSITIVE_EXAMPLES = [
    "Doctor's appointment",
    "Take my medication",
    "Take my blood pressure pills",
    "Refill my heart medication",
    "Pick up my prescription from the pharmacy",
    "Blood test results appointment",
    "Therapy session",
    "Mental health counselling appointment",
    "Dentist appointment",
    "Hospital check-up",
    "Call the clinic about my test results",
    "Physiotherapy session",
    "Pay the credit card bill",
    "Bank meeting about my loan",
    "Transfer money for the rent",
    "Meeting with my lawyer",
    "Court hearing date",
    "Job interview",
]
# Broad everyday coverage - meals, chores, work, social - so common benign
# reminders have a good anchor to match instead of falling through to sensitive.
NONSENSITIVE_EXAMPLES = [
    "Buy milk",
    "Buy groceries from the store",
    "Buy bread and eggs",
    "Water the plants",
    "Water the garden this evening",
    "Drink a glass of water",
    "Take out the trash",
    "Do the laundry",
    "Wash the car",
    "Charge the laptop",
    "Return the library book",
    "Feed the cat",
    "Pick up a parcel from the locker",
    "Book a table for dinner",
    "Have lunch at noon",
    "Grab lunch with a colleague",
    "Cook dinner",
    "Have a snack",
    "Call a friend to say hi",
    "Call mum for a chat",
    "Finish writing the report",
    "Reply to some emails",
    "Go for a walk",
]

# Decision rule for the embedding classifier. A reminder is sensitive only if it
# is genuinely similar to some sensitive example (>= SENSITIVE_ABS_SIM) AND not
# clearly better matched by an everyday one. This is a *specificity* rule: text
# that resembles no known sensitive topic is spoken freely, rather than every
# low-signal or ambiguous phrase defaulting to sensitive (which flagged
# meaningless test phrases). Real medical/financial reminders sit at 0.6-1.0
# against the sensitive prototypes, so they still gate reliably; junk like
# "reminder after 2 minutes" scores ~0.3 and is correctly treated as non-sensitive.
# Raise SENSITIVE_ABS_SIM to speak more freely, lower it to gate more cautiously.
SENSITIVE_ABS_SIM = 0.42
# Benefit of the doubt on a genuine tie: when the two matches are within this
# cosine of each other AND above the absolute bar, keep it sensitive (the
# privacy-safe side of a real coin-flip, e.g. "results on Friday").
SENSITIVE_TIE = 0.04

# HIGH-PRECISION sensitive terms. These words almost never appear in a benign
# reminder, so a match means sensitive on its own - used two ways:
#   1. as an OR-override on top of the embedding classifier (so an explicit
#      medical/financial word can never slip through even if the sentence
#      embedding is diluted by filler, e.g. "anti-depressive pills after 15 min"
#      scored only 0.38 as an embedding but obviously contains "pills"); and
#   2. as the whole classifier in the keyword fallback when the model is absent.
# Deliberately excludes ambiguous words ("bank", "bill", "pay", "court", "rent")
# that also occur in benign contexts or as names - the embedding handles those.
# Word-ish boundaries so "pillow" doesn't match "pill".
_SENSITIVE_PATTERNS = [
    r"doctor", r"\bdr\.?\b", r"medication", r"medicine", r"\bmeds?\b",
    r"\bpills?\b", r"prescription", r"pharmacy", r"clinic", r"hospital",
    r"therapy", r"therapist", r"counsell?or", r"counsell?ing",
    r"psychiatr", r"psycholog", r"dentist", r"\bdose\b", r"\bdosage\b",
    r"anti-?depress", r"antidepressant", r"insulin", r"chemo", r"dialysis",
    r"biopsy", r"diagnosis", r"\bx-?ray\b", r"\bmri\b", r"ultrasound",
    r"blood\s*(test|pressure|sugar)", r"check-?up", r"mental\s*health",
    r"mortgage", r"\bloan\b", r"\btax(es)?\b", r"insurance", r"overdraft",
    r"\bsalary\b", r"lawyer", r"solicitor", r"attorney", r"court\s*hearing",
]
_SENSITIVE_RE = re.compile("|".join(_SENSITIVE_PATTERNS), re.IGNORECASE)


@dataclass
class SensitivityResult:
    """Outcome of classifying one reminder's text."""

    sensitive: bool
    score: float          # signed margin: >0 means "leans sensitive"
    backend: str          # "embedding" or "keyword"
    reason: str           # short human-readable explanation

    @property
    def label(self) -> str:
        return "sensitive" if self.sensitive else "non-sensitive"


class SensitivityClassifier:
    """Embed reminder text and label it sensitive vs non-sensitive.

    Built lazily via :func:`get_classifier` so the (one-time) model load is
    shared by whichever entry point needs it. Falls back to the keyword
    heuristic if the sentence-transformer can't be imported or loaded.
    """

    def __init__(self) -> None:
        self._model = None
        self._sens_emb = None
        self._nons_emb = None
        self.backend = "keyword"
        try:
            self._load_model()
            self.backend = "embedding"
        except Exception as exc:  # ModuleNotFound, offline first-run, torch, ...
            print(
                "[sensitivity] sentence-transformers unavailable "
                f"({type(exc).__name__}: {exc}); using the keyword fallback. "
                "Install it for the real classifier: "
                "`pip install sentence-transformers`.",
                flush=True,
            )

    def _load_model(self) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import

        print(f"[sensitivity] loading text encoder '{MODEL_NAME}'...", flush=True)
        # Prefer the LOCAL cache: once the model is downloaded, never touch the
        # network again, so a HuggingFace Hub outage (e.g. 504s on its metadata
        # HEAD checks) can't stall or break an already-cached model. Only the very
        # first run reaches the network to fetch the ~80 MB weights.
        try:
            self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            print(f"[sensitivity] '{MODEL_NAME}' not in local cache; downloading "
                  "~80 MB (needs network)...", flush=True)
            self._model = SentenceTransformer(MODEL_NAME)
        # Normalised embeddings so a plain dot product is cosine similarity.
        self._sens_emb = self._model.encode(
            SENSITIVE_EXAMPLES, normalize_embeddings=True
        )
        self._nons_emb = self._model.encode(
            NONSENSITIVE_EXAMPLES, normalize_embeddings=True
        )
        print("[sensitivity] text encoder ready.", flush=True)

    def classify(self, text: str) -> SensitivityResult:
        """Classify one reminder string. Empty/blank text -> sensitive."""

        clean = (text or "").strip()
        if not clean:
            return SensitivityResult(
                True, 0.0, self.backend, "empty text -> treated as sensitive"
            )
        if self.backend == "embedding":
            return self._classify_embedding(clean)
        return self._classify_keyword(clean)

    # --- backends ------------------------------------------------------------

    def _classify_embedding(self, text: str) -> SensitivityResult:
        import numpy as np

        emb = self._model.encode([text], normalize_embeddings=True)[0]
        sens_sims = self._sens_emb @ emb
        nons_sims = self._nons_emb @ emb
        s_i = int(np.argmax(sens_sims))
        n_i = int(np.argmax(nons_sims))
        s_best = float(sens_sims[s_i])
        n_best = float(nons_sims[n_i])
        margin = s_best - n_best
        # Sensitive if it actually resembles a sensitive topic AND an everyday
        # example doesn't clearly beat it (see SENSITIVE_ABS_SIM)...
        sensitive = s_best >= SENSITIVE_ABS_SIM and margin >= -SENSITIVE_TIE
        # ...OR it contains an explicit high-precision sensitive term the
        # sentence embedding may have diluted with filler. Keywords only ever
        # escalate to sensitive; they never downgrade.
        kw = _SENSITIVE_RE.search(text)
        if sensitive:
            reason = (f"resembles sensitive example {SENSITIVE_EXAMPLES[s_i]!r} "
                      f"(cos {s_best:.2f}, everyday best {n_best:.2f})")
        elif kw:
            sensitive = True
            reason = (f"sensitive keyword {kw.group(0)!r} "
                      f"(embedding-only score was {s_best:.2f})")
        elif s_best < SENSITIVE_ABS_SIM:
            reason = (f"no strong match to a sensitive topic "
                      f"(best sensitive cos {s_best:.2f} < {SENSITIVE_ABS_SIM:.2f}); "
                      f"nearest everyday {NONSENSITIVE_EXAMPLES[n_i]!r}")
        else:
            reason = (f"better matched by everyday example "
                      f"{NONSENSITIVE_EXAMPLES[n_i]!r} (cos {n_best:.2f} vs "
                      f"sensitive {s_best:.2f})")
        return SensitivityResult(sensitive, margin, "embedding", reason)

    def _classify_keyword(self, text: str) -> SensitivityResult:
        m = _SENSITIVE_RE.search(text)
        if m:
            return SensitivityResult(
                True, 1.0, "keyword", f"matched sensitive keyword {m.group(0)!r}"
            )
        return SensitivityResult(
            False, -1.0, "keyword", "no sensitive keyword matched"
        )


_CLASSIFIER: SensitivityClassifier | None = None


def get_classifier() -> SensitivityClassifier:
    """Return the process-wide classifier, building it on first call."""

    global _CLASSIFIER
    if _CLASSIFIER is None:
        _CLASSIFIER = SensitivityClassifier()
    return _CLASSIFIER


def classify(text: str) -> SensitivityResult:
    """Convenience: classify ``text`` with the shared classifier."""

    return get_classifier().classify(text)


if __name__ == "__main__":
    # Quick self-test / tuning aid: `python -m robot.core.sensitivity`
    clf = get_classifier()
    print(f"[sensitivity] backend = {clf.backend}\n")
    samples = [
        "Doctor's appointment tomorrow",
        "Take medication at 8 PM",
        "Buy milk",
        "Water the plants",
        "Pick up prescription from the pharmacy",
        "Return the library book",
        "Pay the electricity bill",
        "Call grandma on Sunday",
    ]
    for s in samples:
        r = clf.classify(s)
        print(f"  {r.label:>13}  (margin {r.score:+.2f})  {s!r}\n"
              f"                 {r.reason}")
