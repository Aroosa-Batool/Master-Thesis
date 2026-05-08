// Hardware sanity check for Bangle.js.
//
// Confirms the four things our thesis needs from the watch:
//   1. Screen draw      (output channel for the "watch notification" behavior)
//   2. Vibration motor  (private alert channel)
//   3. Accelerometer    (movement signal for proxy state)
//   4. Heart-rate sensor (bpm signal for proxy state)
//
// How to run:
//   - Open the Espruino Web IDE (https://www.espruino.com/ide/) in Chrome/Edge.
//   - Connect to the Bangle over Web Bluetooth.
//   - Paste this file into the right-hand editor and click "Send to Espruino".
//   - Watch the IDE console (left pane) for [1/4]..[4/4] log lines.
//   - The watch screen also shows step count and a final bpm reading.

// Take over the screen so the clock app stops redrawing on top of us,
// and make sure the LCD is unlocked + powered so anything we draw is visible.
Bangle.setUI();
Bangle.setLocked(false);
Bangle.setLCDPower(1);

function show(line1, line2) {
  g.reset();
  g.clear();
  g.setFont("Vector", 20);
  g.drawString(line1, 10, 40);
  if (line2) g.drawString(line2, 10, 80);
  g.flip();
}

show("Sanity check", "starting...");

// 1. Buzz once to confirm the vibration motor works.
Bangle.buzz(300).then(function () {
  console.log("[1/4] buzz: OK");
});

// 2. Wait for one real accelerometer event. (getAccel() can return a stale
// all-zero cache on a freshly-connected watch.)
var accelHandler = function (a) {
  console.log("[2/4] accel:", a);
  Bangle.removeListener("accel", accelHandler);
};
Bangle.on("accel", accelHandler);

// 3. Cached health status: steps + activity since the last sample.
var health = Bangle.getHealthStatus("last");
console.log("[3/4] health:", health);
show("steps: " + health.steps, "moved: " + health.movement);

// 4. HRM has to be powered on. Log every reading as it arrives so we can see
// the sensor responding even before it locks. Stop on the first confident one.
Bangle.setHRMPower(1, "sanity");
console.log("[4/4] HRM warming up... (wear the watch snug on your wrist)");

var hrmCount = 0;
var hrmHandler = function (hrm) {
  hrmCount++;
  console.log("    HRM[" + hrmCount + "]: bpm=" + hrm.bpm + " conf=" + hrm.confidence);
  if (hrm.confidence >= 30) {
    show("bpm: " + hrm.bpm, "conf: " + hrm.confidence);
    Bangle.removeListener("HRM", hrmHandler);
    Bangle.setHRMPower(0, "sanity");
  }
};
Bangle.on("HRM", hrmHandler);

// Safety: stop trying after 60s so the HRM doesn't stay on forever.
setTimeout(function () {
  Bangle.removeListener("HRM", hrmHandler);
  Bangle.setHRMPower(0, "sanity");
  console.log("    HRM: timed out after 60s with no confident reading");
}, 60000);
