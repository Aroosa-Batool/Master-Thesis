# Master's Thesis Proposal

**Privacy-Aware Interactive Robot for Context-Sensitive Wellbeing Support Using Bangle.js and Ohbot**

## Problem statement

Interactive wellbeing systems often sense user state, but they do not sufficiently address how
private information should be communicated in social settings. A robot should not only detect
that support is needed, but also decide how much to reveal and through which channel.

This thesis addresses the problem of building a robot that adapts its response to both the
user's condition and the surrounding social context, while preserving privacy.

## Proposed system

Three parts:

- **Bangle.js smartwatch** — provides user-related signals and serves as a private notification
  channel.
- **Intermediate interface** — receives smartwatch data, converts it into simplified proxy
  states, and allows manual input of tie strength.
- **Ohbot robot** — uses the proxy state and tie information to select one of four behaviors:
  - **Full disclosure** — explicit verbal response
  - **Partial disclosure** — indirect or reduced verbal response
  - **No disclosure** — no sensitive information revealed
  - **Watch notification** — private message through the smartwatch

## Proposed timeline

| Month | Tasks |
| ----- | ----- |
| 1     | Early plausibility and feasibility check: confirm Bangle.js can provide the needed signals and bidirectional communication between the watch and Ohbot can be established. |
| 2     | Refine thesis scope, review literature, finalize research questions, define privacy constraints, proxy states, and the four robot behaviors. |
| 3     | Design the architecture and build the first pipeline between Bangle.js, the intermediate interface, and Ohbot. Add manual input for tie strength. |
| 4     | Implement the robot behavior logic and map situations to the four response types. Test scenarios with strong-tie and weak-tie settings. |
| 5     | Run early evaluation/pilot tests, refine the interaction logic, fix technical issues, and improve the privacy-aware behavior selection. Qualitative and quantitative analysis with real participants. |
| 6     | Write and finalize the thesis, document system design and findings, prepare final demo and submission. |
