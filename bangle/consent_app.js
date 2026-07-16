// consent_app.js -- Bangle.js: private consent prompt + wrist notifications.
//
// Provides a wrist-side consent channel for the thesis "watch as
// private disclosure channel" pipeline. The watch:
//
//   - Exposes a global `consent(id, msg)` function. When the laptop
//     sends a line like `consent("p17","Allow private reminder?")` to
//     the UART, Espruino's REPL evaluates it, the watch buzzes and
//     shows a Yes/No prompt, and the answer comes back as a single
//     line: "CONSENT:p17:YES" or "CONSENT:p17:NO". The id is a free-
//     form correlation token chosen by the laptop.
//   - Exposes a global `notify(msg)` function that shows a one-way
//     private note on the wrist (used to deliver a reminder privately).
//
// The watch stays connected over BLE; the laptop uses that link as the
// owner-presence signal. (The earlier heart-rate broadcast was removed -
// reminders are now the only trigger.)
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
// result line, plus a stray ">" prompt prefixed onto the next line,
// breaking the line parser. echo(0) keeps the wire clean.
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

// Idle screen shown between prompts: just confirms the consent channel is
// live. A consent()/notify() call takes over the screen and restoreScreen()
// brings this back afterwards.
function redraw() {
  g.reset();
  g.clear();
  g.setFont("Vector", 22);
  g.drawString("Robot linked", 10, 40);
  g.setFont("Vector", 16);
  g.drawString("consent ready", 10, 90);
  g.flip();
}

var redrawTimer = setInterval(redraw, 1000);
redraw();

// Called by the laptop over UART. Pauses the idle redraw, buzzes, and shows a
// touch Yes/No prompt; the answer is sent back as one CONSENT line keyed by
// `id` so the laptop can correlate replies.
//
// Robustness (this used to be broken): the laptop asks one prompt at a time
// and gives up after ~30 s, but E.showPrompt stays on screen until tapped. The
// old design left `pendingConsent` set forever if the user never tapped, then
// auto-replied NO to EVERY future request. Two mechanisms prevent that now:
//   - CONSENT_MS timeout: an unanswered prompt auto-dismisses and clears
//     pendingConsent WITHOUT sending a reply (the laptop treats no-answer as a
//     safe non-disclosure and does not cache it), so the next request gets a
//     fresh prompt; and
//   - a `uiSeq` token: showing a new prompt/note bumps the token, so a
//     superseded prompt's late tap/reject/timeout callbacks become no-ops
//     instead of corrupting the current prompt's state.
var CONSENT_MS = 30000;   // auto-dismiss an unanswered prompt (~laptop timeout)
var pendingConsent = null;
var uiSeq = 0;            // bumped each time a prompt/note takes over the screen
var uiTimer = null;

function restoreScreen() {
  // Bring back the idle "Robot linked" screen after a prompt/note clears.
  if (!redrawTimer) {
    redrawTimer = setInterval(redraw, 1000);
  }
  redraw();
}

function consent(id, msg) {
  var seq = ++uiSeq;      // this prompt now owns the screen
  var handled = false;    // fires once (guards tap-vs-timeout race)
  if (uiTimer) { clearTimeout(uiTimer); uiTimer = null; }
  pendingConsent = id;
  if (redrawTimer) {
    clearInterval(redrawTimer);
    redrawTimer = null;
  }
  Bangle.buzz(400);
  // finish() runs for whichever of tap / firmware-reject / timeout comes first.
  // answer === null means "timed out - send nothing". The seq guard drops it if
  // a newer prompt has already superseded this one.
  function finish(answer) {
    if (handled || seq !== uiSeq) return;
    handled = true;
    if (uiTimer) { clearTimeout(uiTimer); uiTimer = null; }
    if (answer !== null) {
      Bluetooth.println("CONSENT:" + id + ":" + answer);
    }
    pendingConsent = null;
    restoreScreen();
  }
  uiTimer = setTimeout(function () {
    E.showPrompt();        // remove the unanswered prompt
    finish(null);
  }, CONSENT_MS);
  E.showPrompt(msg, {
    title: "Robot asks",
    buttons: { "Yes": 1, "No": 0 }
  }).then(function (answer) {
    finish(answer ? "YES" : "NO");
  }).catch(function (err) {
    finish("NO");
  });
}

// Called by the laptop over UART, like consent(), but one-way: it shows a
// PRIVATE message on the watch and sends nothing back. Used to deliver a
// reminder privately to the wrist when the user tapped No to disclosure - so
// the owner still gets the information, just privately here instead of spoken
// aloud in front of the bystander.
//
// A note supersedes any prompt on screen: it bumps uiSeq (neutralising a stale
// consent prompt's callbacks), cancels the consent timeout, and clears
// pendingConsent - so it also self-heals a consent prompt the user never
// dismissed. Buzzes, shows the note with a single OK button, and restores the
// idle screen once acknowledged.
function notify(msg) {
  var seq = ++uiSeq;
  if (uiTimer) { clearTimeout(uiTimer); uiTimer = null; }
  pendingConsent = null;
  if (redrawTimer) {
    clearInterval(redrawTimer);
    redrawTimer = null;
  }
  Bangle.buzz(400);
  function restore() {
    if (seq !== uiSeq) return;
    restoreScreen();
  }
  E.showPrompt(msg, {
    title: "Private note",
    buttons: { "OK": 1 }
  }).then(restore).catch(restore);
}
