// consent_app.js -- Bangle.js: HR broadcast + private consent prompt.
//
// Extends hrm_broadcast.js with a wrist-side consent channel for the
// thesis "watch as private disclosure channel" pipeline (stage 5 of the
// brief in docs/). Two things happen on the watch:
//
//   1. Continuously broadcast "BPM:<n>" lines over Nordic UART, same as
//      hrm_broadcast.js.
//   2. Expose a global `consent(id, msg)` function. When the laptop
//      sends a line like `consent("p17","Allow private reminder?")` to
//      the UART, Espruino's REPL evaluates it, the watch buzzes and
//      shows a Yes/No prompt, and the answer comes back as a single
//      line: "CONSENT:p17:YES" or "CONSENT:p17:NO". The id is a free-
//      form correlation token chosen by the laptop.
//
// HOW TO RUN:
//   1. Open https://www.espruino.com/ide/ in Chrome/Edge.
//   2. Connect to the Bangle over Web Bluetooth (top-left icon).
//   3. Paste this file into the right-hand editor.
//   4. Click "Send to Espruino" (storage icon). Optionally run `save()`
//      in the left REPL so it survives a reboot.
//   5. Disconnect the IDE so the laptop demo can claim the link.
//
// Why echo(0): with the default REPL echo on, every character we send
// from the laptop ("consent(...)") gets reflected back on the same UART
// the laptop is reading - we'd see ">consent(...)" plus an "=undefined"
// result line, plus a stray ">" prompt prefixed onto the next BPM
// frame, breaking the line parser. echo(0) keeps the wire clean.
//
// We call echo(0) once at module load AND from NRF.on('connect', ...)
// because Espruino re-enables echo on every new BLE connection
// (default behavior - the REPL wants to be friendly to a human pasting
// commands from the Web IDE). For a programmatic consumer like our
// laptop demo we want it silent on every reconnect too.

echo(0);
NRF.on('connect', function () { echo(0); });

Bangle.setLCDPower(1);
Bangle.setLocked(false);

// "broadcast" tag lets us turn the HRM off by name later without
// touching other parts of the OS.
Bangle.setHRMPower(1, "broadcast");

var lastBpm = 0;
var lastBpmTime = 0;
var lastConf = 0;
var lastLogMs = 0;
// If we don't get a confident reading for this long, the displayed bpm
// is treated as stale and we show "no signal".
var STALE_MS = 10000;

Bangle.on("HRM", function (hrm) {
  lastConf = hrm.confidence;
  if (hrm.confidence < 30) return;
  lastBpm = hrm.bpm;
  lastBpmTime = Date.now();
  // Bluetooth.println is the ONLY thing we want on the UART. The
  // earlier console.log() debug line went to the same console (BLE
  // when connected) and polluted the laptop's line parser, so it's
  // gone - the laptop already logs every BPM frame it parses.
  Bluetooth.println("BPM:" + hrm.bpm);
});

function redraw() {
  g.reset();
  g.clear();
  g.setFont("Vector", 22);
  g.drawString("HR broadcast", 10, 30);
  g.setFont("Vector", 32);
  var stale = !lastBpm || (Date.now() - lastBpmTime) > STALE_MS;
  g.drawString(stale ? "no signal" : lastBpm + " bpm", 10, 70);
  g.setFont("Vector", 14);
  g.drawString("conf " + lastConf, 10, 130);
  g.flip();
}

var redrawTimer = setInterval(redraw, 1000);
redraw();

// Called by the laptop over UART. Pauses the HR redraw, buzzes, and
// shows a touch Yes/No prompt. The answer is sent back as a single
// CONSENT line keyed by `id` so the laptop can correlate concurrent
// prompts (only one is expected at a time, but the id makes the
// protocol robust to retries or stale replies).
//
// pendingConsent guards re-entrancy: if a second consent() arrives
// while the first prompt is still on screen, we immediately reply NO
// for the new id and skip the UI. Without the guard, two overlapping
// E.showPrompt calls would each schedule their own .then closure,
// leak setInterval handles, and only the topmost prompt would be
// actionable - the user would answer one prompt and see a stale
// message underneath.
var pendingConsent = null;
function consent(id, msg) {
  if (pendingConsent !== null) {
    Bluetooth.println("CONSENT:" + id + ":NO");
    return;
  }
  pendingConsent = id;
  if (redrawTimer) {
    clearInterval(redrawTimer);
    redrawTimer = null;
  }
  Bangle.buzz(400);
  // done() centralises cleanup so both resolve and reject paths
  // restore the HR redraw exactly once and always send a reply.
  // Without the .catch, a rejected prompt (e.g. the firmware tears
  // down showPrompt under the hood) would leave the watch UI frozen
  // with no HR redraw and no CONSENT line to the laptop, so the
  // demo's worker would just time out and the watch screen would
  // stay stuck until the next reboot.
  function done(answer) {
    Bluetooth.println("CONSENT:" + id + ":" + answer);
    pendingConsent = null;
    if (!redrawTimer) {
      redrawTimer = setInterval(redraw, 1000);
    }
    redraw();
  }
  E.showPrompt(msg, {
    title: "Robot asks",
    buttons: { "Yes": 1, "No": 0 }
  }).then(function (answer) {
    done(answer ? "YES" : "NO");
  }).catch(function (err) {
    done("NO");
  });
}
