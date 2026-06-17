# Repository Agent Instructions

These instructions apply to the whole repository. System, developer, and direct user
instructions override this file.

## Branch Policy

- Work directly on `main`.
- Do not create or switch to feature branches unless the user explicitly asks for one.
- Before editing, check `git status --short --branch`. If the checkout is not on `main`
  and the worktree is clean, switch to `main` and fast-forward from `origin/main`.
- If uncommitted work exists on another branch, preserve it and move it to `main`
  without rewriting or discarding user changes.

## Project Rules

- Keep market-data integrations read-only. Do not add trading credential handling or
  order-placement behavior.
- Keep real secrets in ignored `.env`; add only placeholders and documented knobs to
  `.env.example` and Docker Compose.
- Add targeted tests before implementing behavior changes, then run focused tests and
  the full verification suite before pushing.
- Use Lore-style commit messages for commits.

## MOEX And Russian Market Work

- Learn `/home/elijah/Desktop/moexalgo` before changing MOEX/Russian market behavior.
- If current upstream behavior matters, fetch `https://github.com/moexalgo/moexalgo`
  and compare the local clone before implementing.
- Prefer this repo's existing historical store, job, scheduler, and API patterns over
  new storage or background-processing abstractions.
- FUTOI data is read-only, APIM-backed, stored historically, and retained for the
  latest two years unless the user changes that requirement.
