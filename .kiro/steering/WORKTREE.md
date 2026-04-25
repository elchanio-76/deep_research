---
inclusion: always
---

## Git Worktree & Branch Setup

All work related to the FastAPI backend refactor MUST take place in the dedicated worktree and branch — never on `main`.

- Worktree path: `/home/lchanio/projects/deep-research-fastapi`
- Branch: `fastapi-refactor`

Before making any changes, verify the active branch:

```bash
git branch --show-current
```

If the output is not `fastapi-refactor`, switch to the correct worktree before proceeding:

```bash
cd /home/lchanio/projects/deep-research-fastapi
```

Do NOT commit or apply changes to the `main` branch or any other worktree unless explicitly instructed.
