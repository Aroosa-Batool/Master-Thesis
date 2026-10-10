# University LimeSurvey transfer

`university-survey.txt` is a UTF-8 tab-separated LimeSurvey structure file built from the participant booklet. It contains 154 items, including explanatory displays, in 11 groups. Upload using **+ → Import**; keep **Convert resource links and expression fields** checked. Import creates a new survey rather than overwriting an existing one.

`story-images.zip` contains the gender-neutral home and office illustrations. Import it through the new survey’s **Settings → Resources**. Its `images/` directory matches the links in the questionnaire. Ohbot faces Sam, the bystander, in every panel.

The questionnaire uses the booklet’s fixed assignment **L1-A-W1**. It does not implement random allocation to all 36 experimental assignments. It remains an inactive research draft. Add your university-approved participant information and consent before activation, and review the full participant preview.

Opinion and demographic questions are optional. Agreement items use codes 1–7 and NA. `question-manifest.json` records original labels and portal answer codes; an omitted answer is distinct from NA. Underscores were removed from question codes for LimeSurvey compatibility.

Rebuild with `python3 user-study/limesurvey/build_import.py`. The builder uses the exported blank survey structure from Downloads to preserve the server’s accepted column format. It does not send network requests.
