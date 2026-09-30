# Chief of Staff demo in Perplexity

Use Perplexity Computer with the Custom local Qwen3.6-35B-A3B model. Start a fresh conversation; the installed Chief of Staff skill is discovered automatically. Its scripts, Python, notes, and seed credentials are bundled inside the installed skill folder. The initialization prepares writable token and snapshot copies in `.chief-of-staff-state` inside the current thread workspace. No Desktop folder access is needed by the configured commands.

The current test uses the condensed `editors_day_gtc_demo` skill at commit `3e161d7`. Run only the first prompt manually in a fresh local Computer conversation:

> Good morning chief of staff, what should we work on today?

The briefing script uses the source branch's assumed 9:30 AM demo planning time. The manager's callout is a standard Markdown blockquote with a bold link, without a GitHub alert marker.

Check that the briefing completes, the three sections appear, and the callout has no raw alert syntax. The assistant has only run offline checks; the live Perplexity prompt is left for manual testing. Do not reset the workspace, update trackers, create drafts, or create schedules during this test.

Second Brain uses the existing bundled notes. Credentials, notes, and runtime state are preserved during the skill update.
