---
inclusion: always
---

## Git Worktree & Branch Setup

All work related to the export formats refactor MUST take place in the dedicated  branch — never on `main`.

- Branch: `export-formats`

Before making any changes, verify the active branch:

```bash
git branch --show-current
```

If the output is not `export-formats`, switch to the correct branch before proceeding:

```bash
git switch export-formats
```

Do NOT commit or apply changes to the `main` branch or any other worktree unless explicitly instructed.
