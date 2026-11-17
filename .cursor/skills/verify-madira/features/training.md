# Staff training

Staff training has three mode buttons. Quiz grades the seeded answers and shows a score. Briefing, on this demo instance, grades that same quiz again instead of showing lesson cards. Roleplay shows the lesson cards and an ungraded quiz, and the assistant's message does not contain the guest's line.

## Sub-features

- `training-quiz` grades answers `1,2,2,1` and shows the score.
- `training-briefing` runs Staff Trainer and renders a graded quiz card.
- `training-roleplay` runs Staff Trainer and renders lesson cards plus an ungraded quiz.
- `training-stored` appends a quiz attempt for the quiz and briefing runs.

## How to get to it (user POV)

- Choose `Staff training` in the sidebar, or open `http://127.0.0.1:3000/training`.
- On a narrow viewport, choose the `Team` tab.
- The mode group is labelled `Training mode`. The buttons are `[data-testid=training-briefing]`, `[data-testid=training-quiz]`, and `[data-testid=training-roleplay]`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- The submit button is enabled. Open `/training` in a new browser context for each mode. A reload in the same context restores the earlier run's surfaces.

- **Quiz.** Choose `[data-testid=training-quiz]`. `aria-pressed` is `true`. `[data-testid=training-workbench-prompt]` is `Grade the floor quiz with answers 1,2,2,1 for staff name Floor.` Choose `[data-testid=training-workbench-submit]`. `[data-testid=delegate-staff-trainer]` shows `COMPLETE`. `[data-testid=quiz-card]` contains `Floor quiz — autumn pairings`. `[data-testid=quiz-score]` is `Score 100% (4/4)`. The first prompt in the card is `A guest orders the Dungeness crab and wants wine. What do you open first?` and the marked line is `Correct. Saline, high-acid Muscadet cuts sweet crab and yuzu.`
- **Quiz read back.** `curl -sS http://127.0.0.1:8123/training/progress` includes an attempt `staff_name` `Floor`, `score` 100, `answers` `[1, 2, 2, 1]`.
- **Briefing.** On `/training` in a new browser context, choose `[data-testid=training-briefing]`. The prompt is `Deliver today's pairing briefing, wine-knowledge lesson, and service etiquette for waitstaff and bartenders.` Run specialists. The assistant message names `staff-trainer`. The only custom surface in the response is a `QuizCard`. The page shows `Quiz result · 100.0%` and `[data-testid=quiz-score]` `Score 100% (4/4)`. `[data-testid=lesson-cards]` is absent. Progress gains another Floor attempt with answers `[1, 2, 2, 1]`.
- **Roleplay.** On `/training` in a new browser context, choose `[data-testid=training-roleplay]`. `aria-pressed` is `true`. The prompt is `Start diner roleplay. Play a skeptical guest who ordered the dry-aged ribeye.` Run specialists. The last `[data-testid=copilot-assistant-message]` is the delegation sentence and does not contain `ribeye` or a guest question. `[data-testid=agent-reply]` does contain `ribeye`: it holds your prompt and the briefing cards too. The response components are `LessonCards` then `QuizCard`. `[data-testid=lesson-cards]` is visible under the heading `Staff briefing`, with cards `Wine service etiquette` (WAITSTAFF), `Explaining flavor profiles to guests` (WAITSTAFF), `Tonight's pairing briefing` (ALL), and `Bar and spirit service` (BARTENDER). `[data-testid=quiz-card]` is the ungraded `Floor quiz — autumn pairings` and `[data-testid=quiz-score]` is absent.
- **Proof.** Screenshot each mode after its own run, on a page that was loaded for that mode.

## Gotchas

- Do not require `[data-testid=lesson-cards]` after the briefing button. This demo run graded the quiz.
- Do not require the skeptical-guest line after the roleplay button. The assistant's text is only the delegation sentence, and the surfaces are the briefing cards plus the ungraded quiz.
- The page keeps its thread. Reloading `/training` in the same browser context brings back the previous run's quiz card and delegation row, which makes a briefing run look like the quiz you just took. Use a new browser context between modes.
- The quiz and briefing runs both insert a `Floor` attempt. Count attempts before and after if you need to tell them apart.
