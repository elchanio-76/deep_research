---
inclusion: always
---

## Git Worktree & Branch Setup

All work related to the bugfix feature MUST take place in the dedicated  branch — never on `main`.

- Branch: `bugfix`

Before making any changes, verify the active branch:

```bash
git branch --show-current
```

If the output is not `bugfix`, switch to the correct branch before proceeding:

```bash
git switch db-migrations
```

Do NOT commit or apply changes to the `main` branch or any other worktree unless explicitly instructed.

## Virtual environment

After switching to the correct branch, ALWAYS ensure that the project's virtual environment is activated, BEFORE proceeding with the rest of your tasks. From the root of the project run:

```bash
source .venv/bin/activate
```
