# Staff training

Staff training drafts a lesson from a service standard, approves it, and lets a server take the quiz. The old three-button quiz, briefing, and roleplay workbench is gone. Roleplay is the practice tab, covered in [Team](./team.md).

## Sub-features

- `training-standards` lists the shipped standards and saves an Owner edit.
- `training-lesson` drafts a server lesson and approves it.
- `training-quiz` has the server answer the quiz and shows the next review date.

## How to get to it (user POV)

- Choose `Staff training` in the sidebar, or the phone `Team` tab, or open `http://127.0.0.1:3000/training`.
- Standards are `[data-testid=standards-link]` or `http://127.0.0.1:3000/training/standards`.
- Source: `frontend/src/app/training/page.tsx`, `frontend/src/app/training/standards/page.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. `[data-testid=training-actor]` contains `Demo Owner`.

- **Standards.** Open `/training/standards`. The heading is `Service standards`. At least one `[data-testid=standard]` is visible. `[data-testid=standard-title]` is an input whose value is `Opening a still bottle`. Leave the text as shipped unless you are checking save. `[data-testid=standard-save]` is on the page for the Owner.
- **Draft.** Open `/training`. `[data-testid=training-actor]` contains `Demo Owner`. Set `[data-testid=lesson-position]` to `server` and choose `[data-testid=lesson-draft]`. On a fresh seed, `[data-testid=training-error]` is `A lesson needs house standards and on-list bottles with approved notes and service cards.` That is the gate in `backend/madira/domain/training/lessons.py`. Approve a tasting note and a service card for a bottle on the newest list, then draft again. The draft card's title includes `Opening a still bottle` (`backend/madira/domain/training/standards.py`). Choose `[data-testid=lesson-approve]`.
- **Quiz.** Choose `[data-testid=tab-lessons]`. A `[data-testid=my-lesson]` contains that title. Switch to Ana (`POST /auth/demo-persona` `{"slug":"ana"}`) and reload `/training`. Open the lesson's `[data-testid=lesson-quiz]`. `[data-testid=quiz-question]` is visible. Choose the first `[data-testid=quiz-choice]` on each question and choose `[data-testid=quiz-submit]`. `[data-testid=quiz-score]` and `[data-testid=quiz-next-review]` are visible. This quiz step stays blocked until the draft above succeeds.
- **Read back.** `curl -sS http://127.0.0.1:8123/training/standards` returns the standards. `GET /training/lessons` includes the approved title after the approve.
- **Restore.** Switch the persona back to `owner`.
- **Proof.** Screenshot the approved lesson and the quiz score.

## Gotchas

- The workbench prompt is still on the page (`training-workbench`). The lesson desk is the proof. Do not wait for the old `[data-testid=training-quiz]` button. It is not in the page.
- Ana does not see the team tab. She does see lessons.
- The quiz score depends on which choice is first. The proof is that a score and a next-review line render, not a fixed 100%. The quiz itself stays unreachable until a listed bottle has an approved note and an approved service card. On a fresh seed the draft stops at the 422 above, so do not look for `[data-testid=lesson-quiz]` until that gate is cleared.
