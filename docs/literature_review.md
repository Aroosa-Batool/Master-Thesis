# Literature Review: Privacy-Aware Interactive Robot for Context-Sensitive Wellbeing Support

This review supports the thesis "Privacy-Aware Interactive Robot for Context-Sensitive Wellbeing Support Using Bangle.js and Ohbot." The system pairs a Bangle.js smartwatch with the Ohbot social robot through an intermediate Python layer, and selects one of four disclosure behaviors (full, partial, none, watch-routed) based on a proxy user state and surrounding social context (bystander presence, tie strength).

All citations below were verified against a publisher page, DOI resolver, arXiv abstract page, or PMC record during preparation. Entries that could not be verified beyond a web-search summary are explicitly marked **[needs verification]**.

## 1. Overview of the research problem

Wellbeing-oriented socially assistive robots increasingly sense user state (heart rate, voice, facial expression) and respond with verbal support, coaching, or companionship. Two trends create the gap this thesis targets. First, sensing has migrated from the robot itself to body-worn devices, so the user's *physiological* state is now legible even when the robot is silent or absent. Second, a parallel HCI literature on bystander privacy in smart homes and on contextual integrity has shown that the appropriateness of an information disclosure is not a property of the data alone, it is a property of *who is in the room*, *who the recipient is*, and *what social norms govern the flow* (Nissenbaum, 2010; Apthorpe et al., 2018; the bystander privacy literature reviewed in this document).

Most existing wellbeing robots collapse these two layers: they act on the user's state but treat the social environment as fixed (a clinic, a private bedroom, a one-on-one therapy session). Likewise, smartwatch wellbeing systems are usually self-contained — they nudge the wearer but do not coordinate with a co-located embodied agent. The proposed system addresses the seam between them. The robot must reason about *whom an utterance can be heard by* and *what the wearer's relationship to those listeners is* before deciding whether to speak the supportive content out loud, hint at it indirectly, stay silent, or push it privately to the watch. The contribution is therefore not "another wellbeing robot" but a privacy-aware *channel-selection* policy that uses the watch as both a sensor and a private return channel, with tie strength and bystander presence as first-class inputs to the policy.

This problem is distinct from generic wellbeing robots (which assume a fixed audience), generic smartwatch coaches (which lack an embodied co-located agent), and prior privacy-sensitive HRI work (which has mostly studied *whether* a robot should disclose, rather than *via which channel* and at *which level of detail*).

## 2. Thematic literature review

The seven themes overlap substantially. Where a paper supports more than one theme it is cited under the most central one and cross-referenced.

### 2a. Privacy in human-robot interaction

- **Rueben, Grimm, Bernieri, & Smart (2017).** *A Taxonomy of Privacy Constructs for Privacy-Sensitive Robotics.* arXiv:1701.00841. [https://arxiv.org/abs/1701.00841](https://arxiv.org/abs/1701.00841). Decomposes "privacy" into operationalisable sub-constructs (informational, physical, psychological, social) and argues that HRI studies should target one rather than the whole — directly informs how this thesis frames "disclosure" as the informational + social privacy axis.
- **Lutz, Schöttler, & Hoffmann (2019).** *The privacy implications of social robots: Scoping review and expert interviews.* Mobile Media & Communication, 7(3). [https://doi.org/10.1177/2050157919843961](https://doi.org/10.1177/2050157919843961). Maps the design and policy space; useful as a bridging review between robotics, HCI, and law for the thesis introduction.
- **Lutz & Tamò-Larrieux (2021).** *Do Privacy Concerns About Social Robots Affect Use Intentions? Evidence From an Experimental Vignette Study.* Frontiers in Robotics and AI, 8: 627958. [https://doi.org/10.3389/frobt.2021.627958](https://doi.org/10.3389/frobt.2021.627958). Empirically establishes a "robot privacy paradox": stated concerns do not predict use intent. Supports the thesis assumption that a *technical* privacy mechanism (channel selection) may matter more than asking users to set preferences.
- **Dietrich, Krüger, & Weisswange (2023).** *What should a robot disclose about me? A study about privacy-appropriate behaviors for social robots.* Frontiers in Robotics and AI, 10: 1236733. [https://doi.org/10.3389/frobt.2023.1236733](https://doi.org/10.3389/frobt.2023.1236733). 155-participant vignette study finding that *both* relationship proximity and information sensitivity govern appropriate disclosure — neither alone determines it. The single closest precedent for this thesis: same intuition (relation × content), but their setting is robot-as-mediator-between-humans, not robot-as-supporter.
- **Tian, Carreno-Medrano, Allen, Kulić, & Cosgun (2023).** *Effects of Social Behaviors of Robots in Privacy-Sensitive Situations.* International Journal of Social Robotics. [https://doi.org/10.1007/s12369-021-00809-2](https://doi.org/10.1007/s12369-021-00809-2). **[needs verification on full author list — DOI confirmed, but Springer page blocked WebFetch; verified via Semantic Scholar metadata.]**
- **Sullivan, Zhang, Li, Kirkorian, Mutlu, & Fawaz (2025).** *Benchmarking LLM Privacy Recognition for Social Robot Decision Making.* arXiv:2507.16124. [https://arxiv.org/abs/2507.16124](https://arxiv.org/abs/2507.16124). Surveys human privacy preferences (N=450) for in-home robot scenarios, then benchmarks 10 LLMs against them; finds low human–LLM agreement. Frames why a *rule-based* policy (as proposed in this thesis) is defensible relative to an end-to-end LLM controller.

### 2b. Socially assistive robots and wellbeing support

- **Feil-Seifer & Matarić (2005).** *Defining Socially Assistive Robotics.* In Proceedings of the IEEE International Conference on Rehabilitation Robotics (ICORR), pp. 465–468. **[needs verification of DOI; the paper is widely cited and indexed on Semantic Scholar but ICORR 2005 has no canonical DOI page reachable here.]** The foundational definition: SAR = assistive robotics that helps via social rather than physical interaction.
- **Riek (2017).** *Healthcare Robotics.* Communications of the ACM, 60(11), 68–78. [https://doi.org/10.1145/3127874](https://doi.org/10.1145/3127874). Stakeholder/setting/task taxonomy that situates the proposed system in the "informal home wellbeing" cell.
- **Scoglio, Reilly, Gorman, & Drebing (2019).** *Use of Social Robots in Mental Health and Well-Being Research: Systematic Review.* JMIR, 21(7): e13322. [https://doi.org/10.2196/13322](https://doi.org/10.2196/13322). Twelve-study review showing the existing evidence base is small and skewed toward elderly care; supports the thesis claim that the home/social-context cell is under-investigated.
- **Chita-Tegmark & Scheutz (2021).** *Assistive Robots for the Social Management of Health: A Framework for Robot Design and Human–Robot Interaction Research.* International Journal of Social Robotics, 13(2), 197–217. [https://doi.org/10.1007/s12369-020-00634-z](https://doi.org/10.1007/s12369-020-00634-z). Framework arguing that "social management of health" — including how a person presents their health state to others — is itself a robot design target. This is essentially the thesis's framing in different words.
- **Guemghar, Pires de Oliveira Padilha, Abdel-Baki, Jutras-Aswad, Paquette, & Pomey (2022).** *Social Robot Interventions in Mental Health Care and Their Outcomes, Barriers, and Facilitators: Scoping Review.* JMIR Mental Health, 9(4): e36094. [https://doi.org/10.2196/36094](https://doi.org/10.2196/36094). Identifies privacy and surveillance as recurring barriers — direct motivation.

### 2c. Wearable sensing and smartwatch-based wellbeing systems

- **Schmidt, Reiss, Duerichen, Marberger, & Van Laerhoven (2018).** *Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection.* Proceedings of the 20th ACM International Conference on Multimodal Interaction (ICMI '18), pp. 400–408. [https://doi.org/10.1145/3242969.3242985](https://doi.org/10.1145/3242969.3242985). Standard benchmark for the sensor → state mapping the intermediate layer must perform.
- **Pinge, Gad, Jaisighani, Ghosh, & Sen (2024).** *Detection and monitoring of stress using wearables: a systematic review.* Frontiers in Computer Science, 6: 1478851. [https://doi.org/10.3389/fcomp.2024.1478851](https://doi.org/10.3389/fcomp.2024.1478851). Up-to-date map of wrist-only stress pipelines; relevant for justifying the simplified proxy state derived from Bangle.js HRM.
- **Ravanelli, Lefebvre, Brough, Paquette, & Lin (2025).** *Validation of an Open-Source Smartwatch for Continuous Monitoring of Physical Activity and Heart Rate in Adults.* Sensors, 25(9): 2926. [https://doi.org/10.3390/s25092926](https://doi.org/10.3390/s25092926). Validates an open-source smartwatch (Bangle.js 2 family) against Polar H10 for HR and steps — direct evidence that the chosen hardware is research-defensible, not a toy.
- **Schmidt, Reiss, Duerichen, & Van Laerhoven (2018) → reuse under 2c only; cited once.**

### 2d. Context-aware and adaptive robot behaviour

- **Mutlu, Roy, & Šabanović (in *The Social Context of Human–Robot Interactions*, Annual Review of Control, Robotics, and Autonomous Systems, 2024).** **[needs verification — review article located via the Annual Reviews search but exact volume/page/author order could not be confirmed; the review with title "The Social Context of Human–Robot Interactions" exists at the Annual Reviews journal listed.]** Argues that social context (multi-party, role, setting) must be modelled explicitly rather than abstracted away.
- **Aroyo, Pasquali, Kothig, Rea, Sandini, & Sciutti (and colleagues) (2018).** *Themes and Research Directions in Privacy-Sensitive Robotics.* IEEE ARSO 2018. **[needs verification of complete author order — the ULiège archive copy lists Rueben, Aroyo, Lutz, et al. as authors; PDF reachable but binary content prevented direct extraction during this review.]** Provides the seven-theme research roadmap (data privacy, deception, trust, blame, legal, sensitive domains, theory) that this thesis sits inside.
- **Adikari, Cangelosi, & Gomez (2023).** *Social Robot Mediator for Multiparty Interaction.* ICRA 2023 Workshop "Towards a Balanced Cyberphysical Society." arXiv:2310.13508. [https://arxiv.org/abs/2310.13508](https://arxiv.org/abs/2310.13508). Adjacent: a robot that decides what to say in multi-party settings. Their object is conversation flow, not disclosure level — a useful contrast to position the thesis.

### 2e. Privacy-preserving communication and notification channels

- **Langheinrich (2001).** *Privacy by Design — Principles of Privacy-Aware Ubiquitous Systems.* Proceedings of UbiComp 2001, LNCS 2201, Springer. [https://doi.org/10.1007/3-540-45427-6_23](https://doi.org/10.1007/3-540-45427-6_23). Six classical principles (notice, choice, proximity/locality, anonymity, security, access). The "proximity and locality" principle is the closest theoretical anchor to a watch-routed-versus-spoken decision.
- **Hong & Landay (2004).** *An architecture for privacy-sensitive ubiquitous computing.* MobiSys '04, pp. 177–189. [https://doi.org/10.1145/990064.990087](https://doi.org/10.1145/990064.990087). Confab: a toolkit for routing personal information through layered privacy-aware components. The intermediate Python layer in this thesis can be read as a small, special-case Confab.
- **Iachello & Hong (2007).** *End-User Privacy in Human-Computer Interaction.* Foundations and Trends in HCI, 1(1), 1–137. [https://doi.org/10.1561/1100000004](https://doi.org/10.1561/1100000004) **[DOI partially verified via the Foundations and Trends listing on Now Publishers; confirm pagination before final cite.]** Survey covering how disclosure, control, and feedback should be designed.
- **Apthorpe, Shvartzshnaider, Mathur, Reisman, & Feamster (2018).** *Discovering Smart Home Internet of Things Privacy Norms Using Contextual Integrity.* Proceedings of the ACM on IMWUT, 2(2), Article 59. [https://doi.org/10.1145/3214262](https://doi.org/10.1145/3214262). Operationalises Nissenbaum's contextual integrity for IoT, surveying 1,731 adults on whether specific information flows are appropriate. The methodology transfers cleanly to vignette evaluation of the four robot behaviors.

### 2f. Social context, bystanders, and tie strength

- **Granovetter (1973).** *The Strength of Weak Ties.* American Journal of Sociology, 78(6), 1360–1380. [https://doi.org/10.1086/225469](https://doi.org/10.1086/225469). Foundational: defines tie strength (intensity, intimacy, time, reciprocity) and shows weak ties play a structurally distinct role from strong ties. Justifies tie strength as a categorical input variable.
- **Marsden & Campbell (1984).** *Measuring Tie Strength.* Social Forces, 63(2), 482–501. [https://doi.org/10.1093/sf/63.2.482](https://doi.org/10.1093/sf/63.2.482). The companion measurement paper: closeness/intensity is the most reliable single indicator; frequency/duration are noisy. Directly informs the thesis's manual tie-strength input (closeness slider rather than a contact-count proxy).
- **Westin (1967).** *Privacy and Freedom.* New York: Atheneum. (Book, no DOI.) Foundational four-state taxonomy (solitude, intimacy, anonymity, reserve). The four robot behaviors map almost directly onto Westin's states (full disclosure ≈ intimacy; partial ≈ reserve; none ≈ anonymity-protective; watch ≈ solitude-preserving).
- **Altman (1975).** *The Environment and Social Behavior: Privacy, Personal Space, Territory, Crowding.* Brooks/Cole. (Book, no DOI.) Privacy as dynamic boundary regulation — the conceptual basis for treating disclosure level as a per-situation control variable rather than a setting.
- **Palen & Dourish (2003).** *Unpacking "Privacy" for a Networked World.* CHI '03, pp. 129–136. [https://doi.org/10.1145/642611.642635](https://doi.org/10.1145/642611.642635). Applies Altman to networked technologies via three boundary tensions (disclosure, identity, temporality). A clean theoretical scaffold for the thesis's policy logic.
- **Nissenbaum (2010).** *Privacy in Context: Technology, Policy, and the Integrity of Social Life.* Stanford University Press. (Book, no DOI; ISBN 9780804752374.) Contextual integrity. The framework most often cited as the principled justification for varying disclosure with audience, and the natural language in which to phrase the four behaviours.
- **The bystander-privacy review by Yao and colleagues (2024/2025), *Bystander Privacy in Smart Homes: A Systematic Review of Concerns and Solutions*, ACM Transactions on Computer-Human Interaction.** [https://doi.org/10.1145/3731755](https://doi.org/10.1145/3731755) **[needs verification on author list and final pagination — ACM Digital Library page returned 403 and the open NSF-PAR record was not opened in this review session.]** Bystanders (guests, roommates, domestic workers) often have weak agency over devices that record them; the literature converges on automatic deletion, blurring, and consent flows. Directly motivates the "no disclosure" and "watch notification" behaviours.

### 2g. Evaluation methods for privacy-aware interactive systems

- **Riek (2012).** *Wizard of Oz Studies in HRI: A Systematic Review and New Reporting Guidelines.* Journal of Human-Robot Interaction, 1(1), 119–136. [https://doi.org/10.5898/JHRI.1.1.Riek](https://doi.org/10.5898/JHRI.1.1.Riek). Methodological reference for the pilot evaluation stage of the thesis: how to constrain wizard behaviour, how to report.
- **Apthorpe et al. (2018)** (re-listed from 2e). The vignette-based contextual-integrity survey method is the most directly applicable evaluation instrument: the four behaviours can be probed across (sender, recipient, attribute, transmission principle) tuples.
- **Dietrich et al. (2023)** (re-listed from 2a). 155-participant vignette study; same methodological template.
- **Lutz & Tamò-Larrieux (2021)** (re-listed from 2a). Experimental vignette method for measuring privacy concern vs. use intent.

(Themes 2a/2g overlap heavily — vignette-based privacy evaluation in HRI is essentially the same population of papers viewed through different lenses. Rather than duplicate entries I cross-reference.)

## 3. Comparison table

| Paper | Year | Domain | Technology | Privacy mechanism | Social context? | Wearable? | Robot? | Evaluation | Relevance to thesis |
|---|---|---|---|---|---|---|---|---|---|
| Rueben et al. | 2017 | HRI privacy theory | n/a | Taxonomy of constructs | Conceptual | No | No (theoretical) | Literature analysis | Frames "what kind of privacy" |
| Lutz, Schöttler & Hoffmann | 2019 | Social robots policy/HCI | Various | Scoping review | Yes | No | Yes | Expert interviews | Bridging review |
| Lutz & Tamò-Larrieux | 2021 | HRI privacy | Survey | None (measurement) | No | No | Yes | Vignette experiment | Privacy-paradox baseline |
| Dietrich, Krüger & Weisswange | 2023 | Robot mediator | Vignette | Disclosure level | **Yes (relationship + content)** | No | Yes | N=155 vignette | Closest precedent |
| Tian et al. | 2023 | HRI | Pepper | Behavioural mitigation | Yes | No | Yes | Experimental | Privacy-sensitive behaviors |
| Sullivan et al. | 2025 | LLM-robot privacy | LLM | Contextual integrity | Yes | No | Yes (in-home) | Benchmark vs N=450 | LLM-policy comparison |
| Feil-Seifer & Matarić | 2005 | SAR foundations | Theoretical | n/a | Implicit | No | Yes | Definitional | Defines SAR |
| Riek | 2017 | Healthcare robotics | Various | n/a | Yes | Sometimes | Yes | Survey | Stakeholder map |
| Scoglio et al. | 2019 | SAR mental health | Various | Discussed | Limited | Limited | Yes | Systematic review | Evidence-base map |
| Chita-Tegmark & Scheutz | 2021 | SAR framework | Theoretical | Discussed | **Yes** | No | Yes | Framework | Closest framing precedent |
| Guemghar et al. | 2022 | SAR mental health | Various | Identified as barrier | Some | Some | Yes | Scoping review | Privacy-as-barrier evidence |
| Schmidt et al. (WESAD) | 2018 | Affective computing | Empatica E4 + chest | n/a | Lab | Yes | No | Lab benchmark | State-mapping reference |
| Pinge et al. | 2024 | Wearable stress | Various wrist | Discussed | Limited | **Yes** | No | Systematic review | Wrist-stress pipeline map |
| Ravanelli et al. | 2025 | Open wearable validation | Bangle.js 2 | n/a | Lab | **Yes (Bangle)** | No | Validation vs Polar H10 | Hardware credibility |
| Adikari, Cangelosi & Gomez | 2023 | Multi-party HRI | Pepper | None | **Yes (multi-party)** | No | Yes | Workshop position | Adjacent: turn-taking |
| Langheinrich | 2001 | UbiComp privacy | Theoretical | Six principles | Yes | Implicit | No | Conceptual | "Proximity & locality" anchor |
| Hong & Landay | 2004 | UbiComp privacy | Confab toolkit | Architecture | Yes | Yes | No | System | Closest architecture precedent |
| Iachello & Hong | 2007 | HCI privacy | Survey | Many | Yes | Some | No | Survey | Design vocabulary |
| Apthorpe et al. | 2018 | IoT privacy | Survey method | Contextual integrity | **Yes (norms)** | No | No | N=1731 vignette | Evaluation method |
| Granovetter | 1973 | Sociology | n/a | n/a | **Yes (tie strength)** | No | No | Survey | Foundational |
| Marsden & Campbell | 1984 | Sociology | n/a | n/a | **Yes** | No | No | Measurement study | Tie-strength operationalisation |
| Westin | 1967 | Privacy theory | n/a | Four states | Yes | No | No | Conceptual | Maps to four behaviours |
| Altman | 1975 | Privacy theory | n/a | Boundary regulation | Yes | No | No | Conceptual | Dynamic disclosure |
| Palen & Dourish | 2003 | HCI privacy | n/a | Three boundaries | Yes | Yes | No | Conceptual | Networked-privacy framing |
| Nissenbaum | 2010 | Privacy theory | n/a | Contextual integrity | **Yes** | Yes | Some | Conceptual | Theoretical core |
| Yao et al. (bystander review) | 2024/25 | Smart-home privacy | Various | Bystander mechanisms | **Yes (bystanders)** | Some | No | Systematic review | Bystander vocabulary |
| Riek (Wizard of Oz) | 2012 | HRI methods | n/a | n/a | n/a | No | Yes | Method review | Pilot-study guide |

Bold cells highlight the dimensions where each paper has direct, non-trivial coverage.

## 4. Research gap analysis

The thesis sits at the intersection of seven dimensions:

1. **Wearable physiological sensing** — well-covered (Schmidt et al., 2018; Pinge et al., 2024; Ravanelli et al., 2025).
2. **Robot-delivered wellbeing support** — well-covered (Feil-Seifer & Matarić, 2005; Scoglio et al., 2019; Chita-Tegmark & Scheutz, 2021; Guemghar et al., 2022).
3. **Social-context awareness in HRI** — partially covered, mostly for navigation and turn-taking rather than disclosure (Adikari et al., 2023; the Annual Review survey).
4. **Tie strength as an explicit input** — I found *no* HRI paper that takes Granovetter/Marsden tie strength as an algorithmic input variable. Tie strength appears in HRI as a background construct ("strangers vs. caregivers vs. family") but not as a measurable, switchable parameter. This is one of the thesis's clearest contributions.
5. **Multiple discrete disclosure levels (≥3)** — Dietrich, Krüger & Weisswange (2023) is the only paper I verified that explicitly studies disclosure as a graded variable, but they studied it as a vignette-rating exercise, *not* as a runtime policy in a working system. This is the second clear contribution.
6. **Private smartwatch return channel from the robot** — I found no published system that uses the watch as a *fallback output channel* triggered by the robot's privacy reasoning. Watch-to-robot pipelines exist; robot-to-watch fallback as a privacy mechanism does not, in the verified literature.
7. **Privacy-preserving proxy states** — well-grounded conceptually (Langheinrich, 2001; Hong & Landay, 2004) but rarely used as the *interface* between a watch and a robot.

The single closest precedent is **Dietrich, Krüger & Weisswange (2023)**: same intuition (disclosure depends on relationship × content), same theoretical anchor (contextual integrity / privacy as graded), but their robot is a *mediator between two humans*, the input is a vignette, not live sensor data, and there is no second device used as a private channel. Sullivan et al. (2025) come second-closest but propose an LLM controller for an in-home robot's privacy decisions, again without a wearable channel and without tie strength as a structured variable.

**Headline gap.** No verified prior system jointly (a) uses live wearable sensing, (b) chooses among ≥3 discrete disclosure behaviours including a private wearable-routed channel, and (c) parameterises that choice on both bystander presence and a tie-strength input. The thesis can therefore be honestly framed as the first end-to-end demonstration of a wearable-mediated, tie-strength-aware, multi-level disclosure policy in a co-located social robot.

Areas where the thesis is *not* novel: physiological-state inference from a wrist HR sensor, the abstract idea of contextual disclosure, the use of vignette evaluation for HRI privacy, and the use of socially assistive robots for wellbeing.

## 5. Possible thesis directions

Each direction below assumes the same hardware base (Bangle.js + Ohbot + Python interface, presence detection from camera) but differs in scientific question, scope, and evaluation.

### D1. Policy-driven multi-level disclosure (the proposal as written)

- **RQ.** Does a tie-strength × bystander × user-state policy that selects among four disclosure behaviours produce more privacy-appropriate robot responses (as judged by users) than a fixed full-disclosure baseline?
- **Contribution.** End-to-end system + vignette/Wizard-of-Oz study showing the policy is preferred in mixed-company conditions and not penalised in private conditions.
- **Feasibility.** High. The infrastructure already exists (per the README, presence + HR + Ohbot are integrated). The remaining work is the tie-strength input, the policy table, and the watch-routed return channel.
- **Implementation.** Finite-state policy table (no ML). Manual tie-strength input (slider or one-tap "this person is close/known/stranger"). Watch-display message handler.
- **Evaluation.** N≈20–30 within-subjects vignette study of all four behaviours under three social conditions (alone, weak-tie present, strong-tie present), plus ratings of privacy-appropriateness, helpfulness, and trust.
- **Risks.** Bystander detection from a single laptop webcam is fragile; recruiting confederates as bystanders is expensive; tie-strength manipulation is artificial in a lab.

### D2. Bystander-perspective evaluation

- **RQ.** When the robot speaks a wellbeing message in front of a bystander, how does the *bystander* rate appropriateness, intrusiveness, and inferred information about the wearer — as a function of disclosure level and tie strength?
- **Contribution.** Most existing HRI privacy work studies the *primary user*. The bystander-as-evaluator angle plugs directly into the bystander-privacy literature (Yao et al.) and would be relatively novel for embodied (rather than smart-speaker) HRI.
- **Feasibility.** Moderate. Requires both wearer and bystander participants per session.
- **Implementation.** Same as D1, plus a post-session survey instrument for the bystander.
- **Evaluation.** 2 (level: full vs. partial) × 2 (tie: weak vs. strong) within-subjects from the bystander side.
- **Risks.** Recruiting matched dyads; the bystander knows they are being studied which damages ecological validity.

### D3. Tie-strength inference from interaction history

- **RQ.** Can tie strength be *inferred* (rather than entered manually) from short observation of the wearer and the bystander's interaction (turn-taking, addressing, physical proximity)?
- **Contribution.** Removes the manual-input limitation of D1.
- **Feasibility.** Low–moderate for a single thesis. Robust automatic tie-strength inference from ≤1 minute of camera-and-mic observation is itself a research project.
- **Implementation.** Audio + face turn-taking features → small classifier.
- **Evaluation.** Held-out classification accuracy; closing the loop with the disclosure policy is a stretch.
- **Risks.** Likely results in a thin contribution unless a labelled dataset can be constructed cheaply.

### D4. Comparative evaluation: robot voice vs. watch-only

- **RQ.** For elevated-stress events, do users prefer (and act on) robot-spoken support, watch-displayed support, or robot-prompts-watch hybrid?
- **Contribution.** Direct, clean evidence for the *value* of the watch return channel — currently assumed but unevidenced.
- **Feasibility.** High. Drops the four-behaviour complexity and runs a tighter 3-condition study.
- **Evaluation.** Within-subjects, perceived privacy + perceived support + actual behaviour-change uptake.
- **Risks.** Narrower contribution; reduces the thesis's structural-novelty claim.

### D5. Policy sensitivity audit

- **RQ.** How sensitive is user-perceived privacy-appropriateness to misclassifications of (a) bystander presence, (b) tie strength, and (c) user state?
- **Contribution.** Engineering-style robustness analysis; useful for designers of similar systems.
- **Feasibility.** High; uses the system as is and injects controlled errors.
- **Evaluation.** Synthetic error injection + user ratings.
- **Risks.** Less narrative-strong than D1/D2; better as a *chapter* than a whole thesis.

## 6. Improved thesis title suggestions

**Technical / system-oriented**
1. A Wearable-Mediated, Privacy-Aware Disclosure Policy for a Co-Located Social Robot
2. From Wrist to Robot: A Sensor-Driven Pipeline for Context-Sensitive Wellbeing Disclosure
3. Bangle.js + Ohbot: An Architecture for Multi-Channel, Privacy-Adaptive Robot Wellbeing Support

**HRI / user-study-oriented**
4. Who Else Is in the Room? Tie-Strength- and Bystander-Aware Disclosure in a Wellbeing Robot
5. Telling, Hinting, Hiding, or Texting: Four Disclosure Behaviours for a Social Wellbeing Robot
6. When Should a Robot Stay Quiet? Evaluating Privacy-Appropriate Disclosure with Smartwatch Fallback

**Privacy-focused**
7. Contextual Integrity in Embodied Wellbeing Support: A Wearable-Coupled Robot Approach
8. Privacy as Channel Choice: Re-routing Sensitive Wellbeing Cues from Robot to Smartwatch

**Short / clear**
9. Quiet Care: A Privacy-Aware Wellbeing Robot
10. The Discreet Robot

**Academic / formal**
11. Context-Sensitive Disclosure in Socially Assistive Robotics: A Multi-Level Policy Evaluated with Wearable Sensing
12. Tie Strength and Bystander Awareness as Inputs to Robot Disclosure Policy: A Bangle.js–Ohbot Case Study

## 7. Recommended final direction

**Recommendation: D1, with a controlled bystander-condition manipulation borrowed from D2.** Justification:

- D1 is what the existing system was built for; the README confirms presence + HR + Ohbot are already integrated, so the remaining engineering is bounded.
- D1 is the *only* direction that exercises all four behaviours, which is the structural novelty claim; narrowing to D4 forfeits this.
- Adding a single bystander manipulation from D2 (alone vs. one weak-tie confederate vs. one strong-tie confederate, with the participant-supplied tie label) gives the study its independent variable without needing matched dyads.
- D3 is high-risk for a master's-thesis budget. D5 is a strong *appendix* but not a thesis spine.
- D4 should be folded in as one of the four conditions inside D1's evaluation rather than run as a separate study.

## 8. Draft research questions

**Main RQ.** Can a social robot, coupled with a smartwatch and a presence sensor, select among four disclosure behaviours (full / partial / none / watch-routed) in a way that participants judge as more privacy-appropriate than a fixed full-disclosure baseline, across varying social contexts (alone, weak-tie present, strong-tie present)?

**Sub-RQs.**
- SQ1. Which features of the social context — bystander count, bystander tie strength, user physiological state — most strongly predict user-rated privacy-appropriateness of each disclosure level?
- SQ2. Does routing sensitive content to the smartwatch (rather than suppressing it entirely) preserve the *helpfulness* of the wellbeing intervention while reducing the *privacy cost*?
- SQ3. Are user judgments stable across self-rated tie strength and observer-rated tie strength, or does the manual-input requirement introduce systematic bias?
- SQ4. How does the proposed policy compare to a single-decision baseline ("speak vs. stay silent") on perceived trust, perceived intrusiveness, and intent to continue use?

**Optional hypotheses.**
- H1. Full-disclosure-everywhere is rated less privacy-appropriate than the adaptive policy in any condition where ≥1 weak-tie bystander is present.
- H2. The watch-routed channel is rated *as helpful* as full disclosure in alone conditions but is preferred over full disclosure in weak-tie conditions.
- H3. Manual tie-strength input, while artificial, produces inter-condition rating differences that match the predictions of contextual-integrity theory.

## 9. Search keywords

The queries that surfaced the highest-quality results in this review:

- privacy human-robot interaction social robot disclosure HRI
- "What should a robot disclose about me" Frontiers Robotics
- privacy paradox social robot Lutz Tamò-Larrieux
- bystander privacy smart home systematic review
- tie strength Granovetter Marsden Campbell measurement
- contextual integrity Nissenbaum privacy framework
- privacy by design ubiquitous computing Langheinrich principles
- Confab privacy ubicomp Hong Landay
- WESAD multimodal stress affect dataset Schmidt
- Detection and monitoring of stress using wearables systematic review Pinge
- Bangle.js validation open-source smartwatch Polar H10
- socially assistive robotics defining Feil-Seifer Matarić
- assistive robots social management of health Chita-Tegmark Scheutz
- social robot mental health wellbeing scoping review JMIR
- Wizard of Oz HRI evaluation Riek reporting guidelines
- multi-party human-robot interaction mediator
- privacy taxonomy constructs robotics Rueben Smart
- benchmarking LLM privacy social robot decision making

Additional queries worth running but not yet exhausted:

- "robot-to-watch" handoff
- "channel selection" notification wearable robot
- "tie strength" CHI HCI design
- "private channel" wearable smartwatch robot disclosure
- self-disclosure robot longitudinal CHI

## 10. Final output

**Headline gap.** No verified prior system jointly (a) drives a co-located social robot from live wearable sensing, (b) selects among ≥3 discrete disclosure behaviours including a wearable-routed private channel, and (c) parameterises the choice on bystander presence *and* tie strength. Dietrich et al. (2023) is the closest theoretical neighbour; Sullivan et al. (2025) is the closest computational neighbour; neither implements the full pipeline.

**Top 5 papers to read first.**
1. Dietrich, Krüger & Weisswange (2023) — closest precedent; read for the disclosure-as-graded-variable framing.
2. Nissenbaum (2010) — theoretical core; read for the language to phrase the four behaviours.
3. Apthorpe et al. (2018) — best evaluation method to copy.
4. Chita-Tegmark & Scheutz (2021) — closest framing of *why* social-context-aware health support is its own design problem.
5. Sullivan, Zhang, Li, Kirkorian, Mutlu & Fawaz (2025) — current state-of-the-art baseline; useful contrast for justifying a rule-based controller.

**Best 3 titles.**
- "Telling, Hinting, Hiding, or Texting: Four Disclosure Behaviours for a Social Wellbeing Robot" — most communicative.
- "Tie Strength and Bystander Awareness as Inputs to Robot Disclosure Policy: A Bangle.js–Ohbot Case Study" — most academically precise.
- "A Wearable-Mediated, Privacy-Aware Disclosure Policy for a Co-Located Social Robot" — best for a systems-track audience.

**Most promising direction.** D1 (the proposal as written), tightened with a single explicit bystander manipulation borrowed from D2. This keeps all four behaviours in the system, gives a clean independent variable, and is reachable inside a master's-thesis budget given the already-working presence + HR + Ohbot pipeline.
