# Refactoring Skill

## When To Use

Use this when reducing file size, removing dead code, extracting helpers, or splitting modules without changing behavior.

## Checklist

- Lock behavior with tests before moving code.
- Prefer extraction of stable constants and pure helpers before component rewrites.
- Keep imports one-way and avoid circular dependencies.
- Delete duplicated logic after extraction.
- Move styles by page or component responsibility.
- Run the same tests before and after the refactor.

## Verification

- Run targeted tests for the moved behavior.
- Run `npm run frontend:check` for Vue and TypeScript refactors.
- Run `python3 -m unittest discover -v` before pushing.
