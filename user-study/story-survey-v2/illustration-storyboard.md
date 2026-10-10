# Illustration storyboard and image-generation record

## Verified references and remaining hardware assumptions

Reviewed before writing detailed prompts:

- [Official Ohbot v2.2 image](https://learn.ohbot.co.uk/uploads/2/1/8/3/21834178/inthebox_orig.png), linked from [official setup instructions](https://learn.ohbot.co.uk/inst22kit.html): blue acrylic desktop base and skeletal robot head, exposed mechanics, large eyes, separate mouth mechanism.
- [Official camera accessory description](https://www.ohbot.co.uk/product/camera-and-mounting-brackets-for-ohbot) and [mounting instructions](https://learn.ohbot.co.uk/uploads/2/1/8/3/21834178/ohbot_camera_instructions.pdf): an external USB camera with base or headband mounting. The repository describes a head-mounted camera. This does not verify the installed accessory's precise shape or mount.
- [Bangle.js 2 manufacturer documentation](https://www.espruino.com/Bangle.js2): rectangular touchscreen device, single side button, standard strap. Visually inspected [Bangle.js 2 product image from The Pi Hut](https://thepihut.com/cdn/shop/products/bangle-js-2-espruino-104884-32653735035075_1000x.jpg?v=1646637484), a visual reference only; technical claims use the manufacturer documentation.

Public references establish recognizable product forms, not the user's exact unit/version. Confirm actual hardware version, strap and camera appearance before final stimuli. Do not present the generated accessory as an exact measured reproduction. No built-in microphones, lens-eyes, shutters, indicator lights or illuminated rings are inferred. The microphone need not be pictured because its physical location is unverified; its state appears in the caption.

## Equal panel layout

Each story uses three equal-size panels with white gutters, in a 3:1 image block. Both generated assets are 2172×724 pixels. Reuse the **identical bitmap** for M/C/F and Yes/No versions of each setting. Modality is a textual manipulation; do not regenerate a sensor condition independently. This locks people, viewpoint, lighting, expressions, robot/watch shape and rendering style across matched conditions.

| Panel | Picture | Separate readable survey elements |
| --- | --- | --- |
| 1 — context and sensing | Alex and Sam at table; Ohbot and laptop present | Location, relationship, reminder context, prior allowed sensors, actual sensing sequence; ordinary dialogue |
| 2 — private decision | Alex checks/taps Bangle.js, angled away from Sam | Exact existing disclosure prompt, Yes/No buttons and assigned response; sensor stage labels |
| 3 — delivery | Same people and devices, neutral expression | Robot utterance and aloud/private reminder outcome; watch message if private |

S7 reuses home triptych with “Neither sensor” and “Private delivery; no disclosure question” captions. The watch gesture means viewing/acknowledging a private note here, not answering Yes/No. Explain this in the caption. Do not paint a nonexistent question into the screen.

For F in the main stories, the caption explicitly says “Voice detected → camera not activated”. Do not portray a camera scan in those images. The overall silent-visitor fallback example is textual; if it is illustrated later, retain exactly three panels for all versions and use stage labels rather than hardware changes. Text diagrams may show M: microphone → disclosure; C: camera → disclosure; F: microphone → voice found → disclosure, with a separate conditional camera branch labeled “only if no bystander voice detected”. The diagram describes logic, not a visible device light.

All screens remain blank in the generated bitmaps. Render watch wording, buttons and dialogue as selectable HTML or vector text outside the images. This avoids garbled generated text and keeps captions accessible on mobile. Always provide alt text identifying the two people, devices and panel sequence, without claiming a sensor state from visual appearance alone.

## Generated assets

Built-in image-generation tool used on 4 October 2026; two reference-based generations. Assets copied into this package:

- [Home triptych](assets/home-triptych.png), for S1/S3/S5/S7.
- [Office triptych](assets/office-triptych.png), for S2/S4/S6.

The home image was the identity/composition reference for the office image. Exact byte-identical reuse within each matched family removes generation drift between modalities. Human visual review found consistent blue robot, camera accessory, black watch, people, outfits, framing, lighting and neutral expressions. Office changes are mainly the background, though small rendering differences remain across settings. That does not invalidate within-story matching, but location/relationship effects cannot be disentangled. Watch screen is most visible in the decision and outcome panels; do not rely on it for tiny readable text. Final hardware-owner QA remains required.

**Caption under every illustration:** “Hypothetical AI-generated scene. Read the captions for sensing state, watch messages and delivery outcome.”

## Exact prompts used

### Home triptych

Input image roles: reference 1 official Ohbot device appearance only; reference 2 Bangle.js 2 product appearance only.

```text
Use case: scientific-educational. Create a neutral editorial illustration for a hypothetical master's thesis reminder robot survey. Reference 1 is device appearance only: reproduce recognizable blue acrylic Ohbot v2.2 robot head on oval blue desktop base, exposed servos, two large white eyes and curved mechanical mouth; do not copy reference lettering, packaging or cables layout. Reference 2 is Bangle.js 2 device appearance only: black rounded rectangular watch with black strap and single side button, blank screen. Create one wide triptych with exactly THREE equal-sized panels and white gutters, no text anywhere. Same home living room, same people, same robot and watch, same daylight, eye-level viewpoint and calm neutral expressions across all three panels. Owner Alex adult short dark hair wearing plain gray long sleeve top sits at a table beside Ohbot and laptop; visiting friend Sam adult curly brown hair wearing muted green top sits opposite. Both visible, Sam in camera's plausible field of view. Panel 1: the two people converse ordinarily, robot on table. Panel 2: same scene Alex looks at and lightly taps the Bangle.js on left wrist, face of watch angled away from Sam. Panel 3: same scene Alex returns gaze to table, robot neutral. No topic-specific objects. All devices identical across panels. No built-in camera eyes, sensor shutters, status rings or lights; a small external head-mounted USB camera accessory may sit above the head with wire to laptop, identical across all panels. Show no sensor status through hardware; captions added later outside image. No speech bubbles, readable text, numbers, warning symbols, ominous surveillance beams or strong emotional reactions. This same illustration will be reused exactly for all sensing conditions; only surrounding survey captions change.
```

### Office companion

Input image roles: reference 1 generated home triptych for identities, layout and style; reference 2 official Ohbot; reference 3 Bangle.js 2.

```text
Use case: scientific-educational. Create the OFFICE companion to the reference home triptych for a hypothetical reminder robot survey. Image 1 is an exact identity, pose, framing, triptych layout, style and device consistency reference; images 2 and 3 verify Ohbot v2.2 and Bangle.js 2 appearance. Change ONLY the living room background to a quiet ordinary shared office with a desk, shelf and neutral office wall, keeping same daytime light, framing, scale, two adults, outfits, faces, expressions, same laptop, same blue Ohbot with external camera accessory, same black Bangle.js 2 on Alex's left wrist. Sam is now a colleague waiting at the desk. Exactly three equal-width panels with white gutters. Panel 1 two people conversing; panel 2 Alex looking down and tapping watch turned away from Sam; panel 3 Alex looking back toward colleague. Across all panels keep robot device appearance matched. Blank watch screen, no text, no numbers, no symbols, no speech bubbles. No shutters or hardware status lights or invented sensors; no camera eyes. No topic-specific props, no dramatic emotions. Soft neutral editorial realism matching image1. Preserve all device designs and physical proportions. This same triptych will be reused identically for microphone, camera and fallback variants, with captions outside the bitmap.
```

## Proposed future prompt for an actual-hardware revision

Use photographs of the actual Ohbot, installed external camera, actual watch and strap as device references; retain the generated home/office triptych as composition references. Replace only hardware appearance to match those photographs. Preserve people, poses, faces, watch-wearing wrist, room, framing, lighting, panel dimensions and expressions. Remove any accessory feature not shown in actual hardware. Leave screens blank and add all wording through survey rendering. Reuse each approved resulting bitmap across all three sensor conditions; no per-condition raster edits are needed.

## Pilot and final visual QA

Check recognizability against the actual devices; verify visitors could be visible to the mounted camera in the scene; ensure “camera off” captions are understood despite a physically present camera. Pilot comprehension of allowed versus active sensors and of Yes permitting speech. Inspect mobile readability of the external prompt and labels. Keep equal image dimensions and caption layout across all conditions. Check that the neutral facial expressions do not imply satisfaction or distress. Record tool, generation date, exact prompt, reference provenance, selected filenames and any revisions when freezing the stimuli.
