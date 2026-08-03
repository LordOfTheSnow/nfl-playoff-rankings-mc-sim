---
name: commit-msg
description: Generate a commit message from staged changes and commit them. Use when the user says "write a commit message", "generate a commit", "commit my changes", or runs /commit-msg.
---

Follow these steps in order. Do not skip or reorder them.

1. Run `git diff --staged --stat` (or `git diff --staged`) to check whether anything is staged.
   - If there are no staged changes, stop immediately and tell the user to stage changes first (e.g. with `git add`). Do not proceed further, and do not stage anything yourself.

2. Read the full staged diff with `git diff --staged`. Base the message only on what's actually in the staged diff — not on unstaged changes, not on assumptions about intent.

3. Generate a commit message in this exact format:

   ```
   type(scope): short subject

   - bullet of what changed
   - bullet of why
   ```

   - `type` must be one of: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`.
   - `scope` is a short identifier for the area touched (e.g. a module, file, or feature name) — infer it from the diff's paths.
   - `subject` must be under 60 characters, written in imperative mood, no trailing period.
   - Body bullets are optional but encouraged — include them when there's more than one logical change, or when the "why" isn't obvious from the subject alone. Keep bullets concise.
   - Never include a `Co-Authored-By` trailer or any other trailer.

4. Run `git commit -m "$(cat <<'EOF'
   <message>
   EOF
   )"` with the generated message (use a heredoc so multi-line formatting is preserved correctly).

5. Show the user the commit message you used and confirm the commit succeeded (e.g. via `git log -1 --stat` or the commit tool output).

Do not push. Do not amend existing commits. Do not stage additional files beyond what was already staged.
