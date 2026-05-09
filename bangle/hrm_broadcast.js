// hrm_broadcast.js -- Bangle.js: broadcast heart rate over BLE so the
// laptop intermediate layer can read live bpm from the watch.
//
// HOW TO RUN:
//   1. Open https://www.espruino.com/ide/ in Chrome or Edge.
//   2. Connect to the Bangle over Web Bluetooth (top-left icon).
//   3. Paste this whole file into the right-hand editor.
//   4. Click the storage icon ("Send to Espruino").
//   5. To make it survive a reboot of the watch, type at the IDE console:
//        save()
//   6. Wear the watch snug on the wrist for a confident HRM reading.
//
// WHAT IT DOES:
//   Advertises the standard Bluetooth Heart Rate Service (UUID 0x180D) and
//   pushes the latest bpm whenever the on-board HRM produces a confident
//   sample. Standard 2-byte HR Measurement format: [flags, bpm].

Bangle.setLCDPower(1);
Bangle.setLocked(false);

// "broadcast" tag lets us turn the sensor off later by name without
// affecting other parts of the OS.
Bangle.setHRMPower(1, "broadcast");

NRF.setServices(
  {
    "180D": {
      "2A37": {
        readable: true,
        notify: true,
        value: [0x00, 0],
      },
    },
  },
  { advertise: ["180D"], uart: true }
);

var lastBpm = 0;
var lastBpmTime = 0;
var lastConf = 0;
var lastLogMs = 0;

// If we don't get a confident reading for this long, treat the displayed
// bpm as stale and show "no signal" instead.
var STALE_MS = 10000;

Bangle.on("HRM", function (hrm) {
  lastConf = hrm.confidence;
  if (hrm.confidence < 30) return;
  lastBpm = hrm.bpm;
  lastBpmTime = Date.now();
  NRF.updateServices({
    "180D": {
      "2A37": {
        value: [0x00, hrm.bpm],
        notify: true,
      },
    },
  });
  // Throttle console logs to ~once every 5s so the BLE console FIFO stays
  // drainable while the IDE is still connected. The screen still updates
  // every second from redraw().
  var now = Date.now();
  if (now - lastLogMs > 5000) {
    console.log("broadcast bpm=" + hrm.bpm + " conf=" + hrm.confidence);
    lastLogMs = now;
  }
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

setInterval(redraw, 1000);
redraw();
