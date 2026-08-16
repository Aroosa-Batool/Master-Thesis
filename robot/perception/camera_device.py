"""Shared camera-device selection for the camera scripts.

The camera twin of ``audio_device.pick_input_device``. The demo robot's eye is
an **external USB webcam mounted on the Ohbot's head**, and which index that is
cannot be assumed: capture indices are positions in a list whose membership and
order shift underneath us. On macOS an iPhone/iPad in range joins the list as a
Continuity Camera and leaves it again when it wanders off, and the index order
is a *unique-ID sort* (see below) rather than anything a user could guess - so
a hard-coded index silently points at a different eye from one run to the next.

``open_camera()`` resolves the device once, so the two camera apps, the owner
enroller and the eval-set capture tool all open the SAME camera:

  1. ``CAMERA_DEVICE`` when set - a numeric index, or a case-insensitive
     substring of the device name (``CAMERA_DEVICE="HDR webcam"``).
  2. otherwise the first **external** camera - i.e. one that is neither the
     built-in laptop camera nor a phone/tablet Continuity Camera. This is the
     head-mounted webcam whenever it is plugged in.
  3. otherwise index 0, so the demos still run with the webcam unplugged.

Whichever it picks is printed at startup and written to the run's CSV log
(``event=device_selected``), so a trial recording always says which camera saw
it. Pin any camera explicitly with ``CAMERA_DEVICE=<index|name>``.

Device *names* come from the OS, because OpenCV's capture API exposes indices
only - so a name is worth nothing unless we can map it to the index OpenCV will
use. On macOS that order is **not** the order any OS listing shows. OpenCV's
AVFoundation backend builds its device array like this::

    NSArray *devices = [[AVCaptureDevice devicesWithMediaType:AVMediaTypeVideo]
        arrayByAddingObjectsFromArray:
            [AVCaptureDevice devicesWithMediaType:AVMediaTypeMuxed]];
    // then: sortedArrayUsingComparator: [d1.uniqueID compare:d2.uniqueID]
    mCaptureDevice = devices[cameraNum];

so the index is a position in the list **sorted by unique ID string**. On this
lab machine that puts the USB webcam (``0x11400001d6c0103``) at index 0 and the
built-in camera (``6C707041-05AC-...``) at index 1 - the reverse of what
``system_profiler`` and AVFoundation's own listing print, and those listings
additionally float the most recently used camera to the top, which is how
"prefer the external camera" once opened the laptop's. This module therefore
reproduces the sort, reading unique IDs through ``pyobjc-core`` (already
installed - bleak needs it for the watch's BLE link) and falling back to
``system_profiler``'s ``spcamera_unique-id`` field. On Linux the index is the
``/dev/videoN`` number, which is what V4L2 hands OpenCV. A numeric
``CAMERA_DEVICE`` skips name resolution altogether, and
``python -m robot.apps.list_cameras --preview N`` settles any doubt by eye.

``open_camera`` also warms the camera up before returning it: a USB (UVC)
camera needs a few hundred ms of streaming before its first frame arrives, and
without that wait the callers' ``ok, frame = cap.read()`` loops silently spin on
failed reads - or, worse, ``enroll_face`` starts sampling a frame that
auto-exposure has not yet settled.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2

from robot.core.logsetup import logcall, get_logger

log = get_logger(__name__)

# Env overrides. CAMERA_RES is an escape hatch, not routine tuning: the
# per-frame Haar pass measured ~11 ms/frame at 1080p vs ~7 ms at 720p on the
# head camera - both far inside the ~25 fps the camera actually delivers - so
# the default is to take whatever the camera offers and keep the detail.
CAMERA_DEVICE_ENV = "CAMERA_DEVICE"
CAMERA_RES_ENV = "CAMERA_RES"          # e.g. "1280x720"

# How long to wait for the first frame, and how long to keep pulling frames
# afterwards so auto-exposure/auto-white-balance settle before anyone samples.
FIRST_FRAME_TIMEOUT_S = 5.0
SETTLE_S = 0.6

# Mean pixel value below which a frame is "black". A covered lens (privacy
# shutter left closed, camera pressed against the robot's head) still streams
# perfectly good frames at full frame rate - they are just empty, and no face
# will ever be detected in them. Warn rather than fail: a genuinely dark room
# is a legitimate, if unhelpful, condition.
DARK_FRAME_MEAN = 3.0

# Name fragments used to classify a camera. Matched case-insensitively.
_BUILTIN_HINTS = ("facetime", "macbook", "built-in", "builtin", "integrated", "internal")
_CONTINUITY_HINTS = ("iphone", "ipad", "continuity", "desk view")

# Highest index probed when scanning for openable cameras (the lister only).
MAX_PROBE_INDEX = 8

# Every macOS camera call - listing devices as much as opening one - goes
# through CoreMediaIO, and CoreMediaIO can wedge: when its VDCAssistant daemon
# is stuck, +[AVCaptureDevice devicesWithMediaType:] blocks in
# CMIOObjectGetPropertyDataSize forever, with no error and no timeout of its
# own. Observed here as an app that printed nothing after "opening webcam..."
# and had to be killed. These caps turn that freeze into a message that names
# the cause; nothing can make the camera work while the daemon is stuck.
ENUMERATE_TIMEOUT_S = 5.0
OPEN_TIMEOUT_S = 20.0

# What to try when CoreMediaIO is wedged. Printed on timeout, not logged away.
_WEDGED_HELP = (
    "The macOS camera service is not responding (CoreMediaIO).\n"
    "  1. Quit anything else using a camera, and kill any leftover run of these\n"
    "     apps:  pkill -f 'robot.apps'\n"
    "  2. Unplug the USB webcam, including any hub it sits behind.\n"
    "  3. Restart the camera daemons - UVCAssistant is the one that serves USB\n"
    "     cameras, and killing only the other two leaves a stuck one running:\n"
    "       sudo killall -9 UVCAssistant VDCAssistant cameracaptured\n"
    "  4. Replug the webcam, directly into the Mac rather than through a hub.\n"
    "Photo Booth is the quickest check that the camera stack is alive again."
)

# The two AVMediaType constants OpenCV concatenates before sorting, as their
# four-character codes: AVMediaTypeVideo and AVMediaTypeMuxed.
_AVF_MEDIA_TYPES = ("vide", "muxd")


@dataclass(frozen=True)
class CameraInfo:
    """One camera as the OS reports it, at its OpenCV capture index."""

    index: int
    name: str  # "" when the platform does not expose names
    # False when the name came from a source whose order is not guaranteed to be
    # OpenCV's index order (the system_profiler fallback) - the index may be off.
    index_verified: bool = True

    @property
    def builtin(self) -> bool:
        return any(h in self.name.lower() for h in _BUILTIN_HINTS)

    @property
    def continuity(self) -> bool:
        """A phone/tablet acting as a webcam - present only while in range."""

        return any(h in self.name.lower() for h in _CONTINUITY_HINTS)

    @property
    def external(self) -> bool:
        """A real plugged-in camera: the head-mounted USB webcam."""

        return bool(self.name) and not self.builtin and not self.continuity

    def label(self) -> str:
        kind = (
            "external" if self.external
            else "built-in" if self.builtin
            else "continuity" if self.continuity
            else "unknown"
        )
        return f"{self.index} ({self.name!r}, {kind})" if self.name else f"{self.index}"


def _call_with_timeout(fn: Callable[[], object], timeout_s: float, what: str):
    """Run ``fn`` on a daemon thread; return ``None`` if it overruns.

    A CoreMediaIO call that has wedged cannot be cancelled or interrupted, so
    the thread running it is abandoned rather than joined. It is a daemon and
    holds no GIL inside the OS call, so the process still exits normally - what
    we buy is the chance to say what happened instead of hanging forever.
    """

    box: dict[str, object] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True, name=f"camera-{what}")
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        log.warning("%s did not return within %.0fs (CoreMediaIO wedged?)",
                    what, timeout_s, extra={"event": "camera_timeout"})
        return None
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("value")


def _objc_class(name: str):
    """Look up an Objective-C class, loading AVFoundation on first use.

    ``pyobjc-core`` is already installed on macOS - bleak needs it for the
    watch's BLE link - so no framework wrapper package is required. Returns
    None if pyobjc or the class is unavailable.
    """

    try:
        import objc  # noqa: PLC0415 - optional, macOS-only
    except ModuleNotFoundError:
        return None
    try:
        return objc.lookUpClass(name)
    except Exception:  # noqa: BLE001 - class appears only once the bundle loads
        pass
    try:
        objc.loadBundle(
            "AVFoundation", {},
            bundle_path="/System/Library/Frameworks/AVFoundation.framework",
        )
        return objc.lookUpClass(name)
    except Exception as exc:  # noqa: BLE001 - fall back to system_profiler
        log.debug("could not load AVFoundation class %s: %s", name, exc)
        return None


def _avfoundation_devices() -> list[tuple[str, str]]:
    """``(unique_id, name)`` for every camera, as AVFoundation lists them."""

    device_cls = _objc_class("AVCaptureDevice")
    if device_cls is None:
        return []
    devices: list[tuple[str, str]] = []
    for media_type in _AVF_MEDIA_TYPES:
        try:
            found = list(device_cls.devicesWithMediaType_(media_type))
        except Exception as exc:  # noqa: BLE001 - never let listing break a demo
            log.debug("AVFoundation listing for %s failed: %s", media_type, exc)
            continue
        for device in found:
            try:
                devices.append((str(device.uniqueID()), str(device.localizedName())))
            except Exception:  # noqa: BLE001 - skip a device we cannot read
                continue
    return devices


def _system_profiler_devices() -> list[tuple[str, str]]:
    """``(unique_id, name)`` from ``system_profiler`` - used without pyobjc.

    Unique IDs come from the ``spcamera_unique-id`` field, which is the same
    identifier AVFoundation reports, so sorting them reproduces OpenCV's index
    order too. An entry missing that field cannot be placed, and callers then
    mark the whole listing unverified.
    """

    try:
        out = subprocess.run(
            ["system_profiler", "-json", "SPCameraDataType"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("system_profiler camera listing failed: %s", exc)
        return []
    if out.returncode != 0:
        return []
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    return [(str(d.get("spcamera_unique-id", "")), str(d.get("_name", "")))
            for d in data.get("SPCameraDataType", [])]


def _linux_camera_names() -> list[tuple[int, str]]:
    """(index, name) per ``/dev/videoN``; OpenCV's V4L2 index is that N."""

    found: list[tuple[int, str]] = []
    for node in sorted(Path("/sys/class/video4linux").glob("video*")):
        m = re.search(r"(\d+)$", node.name)
        if not m:
            continue
        try:
            name = (node / "name").read_text().strip()
        except OSError:
            name = ""
        found.append((int(m.group(1)), name))
    return sorted(found)


@logcall
def list_cameras() -> list[CameraInfo]:
    """Cameras the OS knows about, in OpenCV index order.

    Empty on platforms we cannot enumerate (Windows), which just means device
    selection falls back to plain indices.
    """

    if sys.platform == "darwin":
        devices = _call_with_timeout(
            _avfoundation_devices, ENUMERATE_TIMEOUT_S, "device listing",
        )
        if devices is None:
            # Do not fall through to system_profiler: it asks CoreMediaIO the
            # same question and would hang on the same wall.
            print(f"[camera] listing cameras timed out.\n{_WEDGED_HELP}", flush=True)
            return []
        verified = True
        if not devices:
            devices = _system_profiler_devices()
        if not devices:
            return []
        # THE mapping: OpenCV indexes this list sorted by unique ID, not in the
        # order the OS printed it. A device with no ID cannot be placed, so the
        # whole listing becomes advisory when one shows up.
        if any(not uid for uid, _ in devices):
            verified = False
        return [CameraInfo(i, name, index_verified=verified)
                for i, (_, name) in enumerate(sorted(devices))]
    if sys.platform.startswith("linux"):
        return [CameraInfo(i, n) for i, n in _linux_camera_names()]
    return []


def describe_cameras(cameras: list[CameraInfo] | None = None) -> str:
    """Human-readable device list for error messages and startup banners."""

    cameras = list_cameras() if cameras is None else cameras
    if not cameras:
        return "  (none could be listed)"
    listing = "\n".join(f"  [{c.index}] {c.name or '<unnamed>'}"
                        + ("   <- external" if c.external else
                           "   (built-in)" if c.builtin else
                           "   (phone/Continuity Camera)" if c.continuity else "")
                        for c in cameras)
    if not all(c.index_verified for c in cameras):
        listing += "\n  (indices unverified - see the note below)"
    return listing


def _warn_unverified(info: CameraInfo) -> None:
    """Say so when a name was mapped to an index we cannot fully trust."""

    if info.index_verified or not info.name:
        return
    print("[camera] NOTE: a camera reported no unique ID, so this name may map to "
          "a different index than OpenCV uses. Confirm with `python -m "
          f"robot.apps.list_cameras --preview {info.index}`, or pin a numeric "
          f"{CAMERA_DEVICE_ENV}.", flush=True)


@logcall
def resolve_camera(
    spec: str | int | None = None, cameras: list[CameraInfo] | None = None,
) -> CameraInfo:
    """Pick the camera to open, without opening it.

    ``spec`` (or ``CAMERA_DEVICE`` when ``spec`` is None) may be an index or a
    case-insensitive name substring; otherwise prefer an external camera, then
    fall back to index 0.

    Pass ``cameras`` when the caller has already listed them: enumeration is a
    trip into CoreMediaIO, which is slow at the best of times and blocks for the
    full timeout when the camera service is stuck - doing it twice for one
    command means twice the wait and the same complaint printed twice.
    """

    if cameras is None:
        cameras = list_cameras()
    want = os.environ.get(CAMERA_DEVICE_ENV) if spec is None else spec

    if want is not None and str(want).strip() != "":
        want = str(want).strip()
        try:
            index = int(want)
        except ValueError:
            matches = [c for c in cameras if want.lower() in c.name.lower()]
            if not matches:
                raise SystemExit(
                    f"[camera] no camera matches {CAMERA_DEVICE_ENV}={want!r}. "
                    f"Cameras found:\n{describe_cameras(cameras)}"
                )
            if len(matches) > 1:
                print(f"[camera] {want!r} matches {len(matches)} cameras; using "
                      f"the first ({matches[0].label()}).", flush=True)
            _warn_unverified(matches[0])
            return matches[0]
        # A numeric override is taken at face value even when the OS listing is
        # shorter (Windows, or a device the listing missed) - OpenCV decides.
        for c in cameras:
            if c.index == index:
                return c
        return CameraInfo(index, "")

    external = [c for c in cameras if c.external]
    if external:
        _warn_unverified(external[0])
        return external[0]
    if not cameras:
        return CameraInfo(0, "")
    # No external camera. Automatic selection deliberately stops here rather than
    # taking the built-in one: the robot's eye is the webcam on its HEAD, and the
    # laptop camera sees a different part of the room and does not move with the
    # sweep. Answering "is a bystander present?" from that view would be worse
    # than not answering. A human can still opt in explicitly via CAMERA_DEVICE.
    raise SystemExit(
        "[camera] no external camera found, and the built-in / phone cameras are "
        "not used automatically - the robot's eye is the webcam mounted on its "
        "head, and the laptop camera points somewhere else and does not move when "
        "the head sweeps.\n"
        "Plug the USB webcam in (directly into the Mac, not through a hub) and "
        "re-run. Cameras found:\n"
        f"{describe_cameras(cameras)}\n"
        f"To use one of these anyway, ask for it explicitly: "
        f"{CAMERA_DEVICE_ENV}=<index|name>."
    )


def _parse_resolution(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", value)
    if not m:
        raise SystemExit(
            f"[camera] {CAMERA_RES_ENV}={value!r} is not WIDTHxHEIGHT (e.g. 1280x720)."
        )
    return int(m.group(1)), int(m.group(2))


def _fallback_order(cameras: list[CameraInfo], exclude: int) -> list[CameraInfo]:
    """The OTHER EXTERNAL cameras to try when the chosen one stays silent.

    Deliberately external-only. The robot's eye is the webcam mounted on its
    head; the laptop's built-in camera points at whoever is sitting at the
    laptop and does not move when the head sweeps, and a phone acting as a
    Continuity Camera points wherever it was left. Substituting either for the
    head camera would answer "is a bystander present?" from the wrong view of
    the room - a wrong answer to the one question the disclosure gate exists to
    ask - so a broken head camera must fail loudly instead. A built-in camera can
    still be used, but only when a human asks for it by name or index through
    ``CAMERA_DEVICE``.
    """

    return sorted((c for c in cameras if c.index != exclude and c.external),
                  key=lambda c: c.index)


@logcall
def _attempt_open(
    info: CameraInfo,
    resolution: tuple[int, int] | None,
    first_frame_timeout_s: float,
    settle_s: float,
) -> tuple[cv2.VideoCapture, "object"] | None:
    """Open ONE camera and prove it delivers. ``None`` if it does not.

    Returns ``(cap, frame)`` - the live capture plus the last warm-up frame, so
    the caller can judge brightness without another read. Never raises for a
    camera that simply does not work; that is the caller's decision to make,
    because on macOS "index 3 is silent" often means the index map moved, not
    that the hardware is broken.
    """

    cap = None
    frame = None
    # A camera released moments ago (enroll_face, then the app) can open again
    # yet stay silent, so a dead first attempt is worth one clean reopen before
    # we give up on this index.
    for attempt in (1, 2):
        # Opening goes through CoreMediaIO too, so it gets the same guard as
        # the listing - otherwise a stuck camera daemon freezes the app here,
        # after the "using device ..." line and before any error.
        cap = _call_with_timeout(
            lambda: cv2.VideoCapture(info.index), OPEN_TIMEOUT_S, "camera open",
        )
        if cap is None:
            # A wedged CoreMediaIO is not an index problem and trying other
            # indices would hit the same wall, so this one still aborts.
            raise SystemExit(
                f"[camera] opening camera {info.label()} timed out after "
                f"{OPEN_TIMEOUT_S:.0f}s.\n{_WEDGED_HELP}"
            )
        if not cap.isOpened():
            cap.release()
            return None
        if resolution is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])

        deadline = time.monotonic() + first_frame_timeout_s
        while time.monotonic() < deadline:
            ok, candidate = cap.read()
            if ok and candidate is not None:
                frame = candidate
                break
            time.sleep(0.02)
        if frame is not None:
            break
        cap.release()
        if attempt == 1:
            print(f"[camera] no frame yet from {info.label()}; reopening once...",
                  flush=True)
            time.sleep(1.0)
    if frame is None:
        return None
    first_frame_at = time.monotonic()

    # Keep the stream running briefly so auto-exposure settles; judge brightness
    # on the last frame of that window, not the first one out of the pipe.
    while time.monotonic() - first_frame_at < settle_s:
        ok, candidate = cap.read()
        if ok and candidate is not None:
            frame = candidate
    return cap, frame


@logcall
def open_camera(
    spec: str | int | None = None,
    *,
    resolution: tuple[int, int] | None = None,
    first_frame_timeout_s: float = FIRST_FRAME_TIMEOUT_S,
    settle_s: float = SETTLE_S,
) -> cv2.VideoCapture:
    """Open a camera that actually delivers frames, and return the live capture.

    EXTERNAL ONLY when choosing automatically. The robot's eye is the USB webcam
    mounted on its head; the laptop's built-in camera watches whoever sits at the
    laptop and stays put while the head sweeps, so it would answer "is a bystander
    present?" from the wrong view of the room. A dead head camera therefore FAILS
    here rather than quietly degrading to the built-in one. If several external
    cameras are attached and the chosen one stays silent, the others are tried.

    A camera pinned EXPLICITLY (``spec`` / ``CAMERA_DEVICE``) overrides all of
    that - including the external-only rule, so the built-in camera is available
    when a human asks for it by name or index - and is never silently swapped for
    another, failing with an actionable message instead.

    Raises ``SystemExit`` when nothing usable could be opened, or when the macOS
    camera service itself is wedged (which no amount of retrying can fix).
    """

    cameras = list_cameras()
    info = resolve_camera(spec, cameras)
    if resolution is None:
        resolution = _parse_resolution(os.environ.get(CAMERA_RES_ENV))
    pinned = bool(
        (spec is not None and str(spec).strip())
        or os.environ.get(CAMERA_DEVICE_ENV, "").strip()
    )

    start = time.monotonic()
    print(f"[camera] using device {info.label()}", flush=True)
    opened = _attempt_open(info, resolution, first_frame_timeout_s, settle_s)

    if opened is None and pinned:
        raise SystemExit(
            f"[camera] camera {info.label()} opened but delivered no frame in "
            f"{first_frame_timeout_s:.0f}s (tried twice).\n"
            f"It was pinned with {CAMERA_DEVICE_ENV}, so no other camera was "
            "substituted. Unplug/replug the USB camera, or pin a different one.\n"
            f"Cameras found:\n{describe_cameras(cameras)}"
        )

    if opened is None:
        alternatives = _fallback_order(cameras, exclude=info.index)
        if alternatives:
            print(f"[camera] {info.label()} delivered no frame; trying the other "
                  "external camera(s)...", flush=True)
            log.warning("camera %d silent; trying other externals", info.index,
                        extra={"event": "camera_fallback"})
        dark_choice: tuple[CameraInfo, cv2.VideoCapture, object] | None = None
        for alt in alternatives:
            time.sleep(0.5)          # let the previous device settle before the next open
            print(f"[camera]   trying {alt.label()}...", flush=True)
            attempt = _attempt_open(alt, resolution, first_frame_timeout_s, settle_s)
            if attempt is None:
                continue
            alt_cap, alt_frame = attempt
            # A phone streaming black "works" but sees nothing; keep looking for a
            # camera with an actual picture, and only settle for a black one if
            # nothing better turns up.
            if float(alt_frame.mean()) >= DARK_FRAME_MEAN:
                info, opened = alt, attempt
                break
            if dark_choice is None:
                dark_choice = (alt, alt_cap, alt_frame)
            else:
                alt_cap.release()
        if opened is None and dark_choice is not None:
            info, alt_cap, alt_frame = dark_choice
            opened = (alt_cap, alt_frame)
        if opened is not None:
            print(f"[camera] switched to the other external camera {info.label()}. "
                  "Confirm it is the head-mounted one with `python -m "
                  f"robot.apps.list_cameras --preview {info.index}`, then pin it "
                  f"with {CAMERA_DEVICE_ENV}={info.index}.", flush=True)
            log.warning("switched to external camera %d (%r)", info.index, info.name,
                        extra={"event": "camera_fallback"})

    if opened is None:
        others = [c.label() for c in cameras if not c.external]
        raise SystemExit(
            f"[camera] the external camera {info.label()} opened but delivered NO "
            f"FRAME in {first_frame_timeout_s:.0f}s (tried twice"
            + (", and so did every other external camera" if _fallback_order(
                cameras, exclude=info.index) else "") + ").\n"
            "The camera reports as connected but is not producing video. Try, in "
            "order:\n"
            "  1. Unplug and replug it - directly into the Mac, not through a hub "
            "(a hub that cannot supply enough power gives exactly this symptom).\n"
            "  2. Close anything else using a camera (Zoom, Teams, Photo Booth, "
            "browser tabs) and check it in Photo Booth.\n"
            "  3. Restart the USB camera daemon:\n"
            "       sudo killall -9 UVCAssistant VDCAssistant cameracaptured\n"
            "\n"
            "The built-in and phone cameras were NOT used instead: the robot's eye "
            "is the webcam on its head, and a camera that sits still while the head "
            "sweeps would answer the who-is-present question from the wrong view.\n"
            + (f"To run anyway on one of {', '.join(others)}, ask for it "
               f"explicitly: {CAMERA_DEVICE_ENV}=<index|name>  (the mic-only "
               "pipeline is the better fallback: --no-camera).\n" if others else "")
            + f"Cameras found:\n{describe_cameras(cameras)}"
        )

    cap, frame = opened
    height, width = frame.shape[:2]
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    warmup_ms = (time.monotonic() - start) * 1000.0
    print(f"[camera] {width}x{height} @ {fps:.0f}fps, first frame after "
          f"{warmup_ms:.0f} ms.", flush=True)
    log.info("camera selected: index=%d name=%r %dx%d fps=%.0f warmup_ms=%.0f",
             info.index, info.name, width, height, fps, warmup_ms,
             extra={"event": "device_selected"})

    mean = float(frame.mean())
    if mean < DARK_FRAME_MEAN:
        print(
            f"[camera] WARNING: frames from {info.label()} are black "
            f"(mean pixel {mean:.1f}/255). Check the lens cap / privacy shutter "
            "and that the camera is not facing the robot's head. No face can be "
            "detected in an all-black frame.",
            flush=True,
        )
        log.warning("camera %d delivers near-black frames (mean=%.2f)",
                    info.index, mean, extra={"event": "camera_dark"})

    return cap


@logcall
def probe_cameras(max_index: int = MAX_PROBE_INDEX) -> list[int]:
    """Indices that actually open, for the lister when names are unavailable.

    Opening a camera is slow and exclusive, so this is a diagnostic tool - the
    apps resolve their device from the OS listing instead.
    """

    openable: list[int] = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            openable.append(index)
        cap.release()
    return openable
