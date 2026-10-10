# Generated-image record

All three raster assets were produced with the built-in image-generation tool on 2026-09-08. They are AI-generated visual vignettes, not photographs, recordings, or exact Ohbot renderings.

## `condition-microphone-only.png`

```text
Use case: scientific-educational
Asset type: matched visual vignette for a master's-thesis participant survey, landscape 4:3
Primary request: create the MICROPHONE-ONLY condition of a privacy-aware social robot user study
Scene/backdrop: calm, ordinary contemporary home-study desk viewed from the seated user's eye level; uncluttered neutral room; a generic small friendly desktop social robot sits on the desk and a smartwatch-wearing forearm rests naturally near it
Subject: the robot has one clearly visible camera lens with a physical shutter fully closed, while a subtle cyan microphone status ring on its base is illuminated; the smartwatch screen is softly awake but contains no readable interface or symbols
Style/medium: polished editorial 3D illustration with believable materials and soft natural texture, accessible research-figure aesthetic, not photorealistic enough to imply a real product
Composition/framing: landscape, centered stable composition, enough clean margin for an HTML caption below; no dramatic perspective
Lighting/mood: soft daylight, calm and emotionally neutral, neither reassuring nor threatening
Color palette: warm off-white and muted navy with cyan active-sensor accent
Constraints: no words, no letters, no numbers, no logos, no watermarks; no recording waves leaving the device; no surveillance imagery; the camera shutter must unmistakably cover the lens; show only one human forearm and no face; do not imply that audio is being saved; keep the design simple enough for later matched variants
Avoid: red warning colors, fear cues, marketing gloss, busy decor, brand resemblance, extra people, readable text
```

## `condition-camera-only.png`

The microphone image was supplied as the edit target.

```text
Use case: precise-object-edit
Asset type: matched visual vignette for a master's-thesis participant survey, CAMERA-ONLY condition
Primary request: edit Image 1 so that only the sensor state changes from microphone-only to camera-only
Input images: Image 1: edit target and exact composition/style reference
Required changes: turn the microphone status ring on the robot's body fully off and unlit; open the physical shutter over the central camera lens so a normal small glass lens is clearly visible; add one subtle cyan status light immediately around the camera lens
Invariants: keep exactly the same robot design, pose, viewpoint, room, desk objects, smartwatch-wearing forearm, crop, daylight, materials, proportions, colors, and neutral mood; keep the smartwatch screen blank; show no other people
Constraints: no words, no letters, no numbers, no logos, no watermarks; no face bounding boxes, beams, recording waves, surveillance graphics, or stored-data implication; only the camera cue is active
Avoid: changing the scene or human hand, red warning colors, fear cues, marketing gloss, readable text
```

## `condition-mic-then-camera.png`

The microphone-only and camera-only images were supplied as matched inputs.

```text
Use case: compositing
Asset type: matched visual vignette for a master's-thesis participant survey, SEQUENTIAL MICROPHONE-THEN-CAMERA condition, landscape 4:3
Primary request: create a clean two-stage diptych using the two supplied matched condition images to show sequence, not simultaneous sensing
Input images: Image 1: microphone-only scene reference; Image 2: camera-only scene reference
Composition: two equal vertical panels with the identical robot, desk, smartwatch-wearing forearm, crop, scale, and daylight; left panel shows microphone ring cyan and camera shutter closed; right panel shows microphone ring gray/off and camera lens open with cyan ring; place one small simple right-pointing chevron between the panels to communicate order
Style/medium: preserve the same polished neutral editorial 3D illustration and believable materials
Invariants: preserve robot identity/design, hand, watch, room, desk objects, colors, neutral mood, and perspective from the supplied images
Constraints: no words, no letters, no numbers, no logos, no watermarks; sensors must never appear active simultaneously; no beams, recording waves, face boxes, surveillance graphics, fear cues, or stored-data implication; smartwatch stays blank
Avoid: changing the person/hand or robot, adding people, red warning colors, readable text, decorative collage styling
```
