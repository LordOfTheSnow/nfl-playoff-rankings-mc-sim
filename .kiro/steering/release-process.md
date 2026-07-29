---
inclusion: manual
---

# Release Process

When asked to prepare a release, follow these steps:

## Version bump

1. Bump `version` in `pyproject.toml`
2. Bump `version` in `uv.lock`
3. Update the version string in `README.md` (`**v0.x.y**`)

## CHANGELOG update

1. Move all items from `## [Unreleased]` into a new section:
   ```
   ## [0.x.y] - YYYY-MM-DD — Short release title
   ```
2. Leave an empty `## [Unreleased]` heading at the top
3. Add link references at the bottom of the file:
   ```
   [Unreleased]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.x.y...HEAD
   [0.x.y]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v<previous>...v0.x.y
   ```

## README ToDo cleanup

If any ToDo items were completed in this release, remove them from the `## ToDo` section.

## Git commands to suggest

After making the changes, suggest:
```bash
git add pyproject.toml uv.lock README.md CHANGELOG.md <other changed files>
git commit -m "Release 0.x.y: short description"
git push -u origin <current-branch>
gh pr create --title "Short release title" --body ""
```

## Notes

- The release workflow triggers automatically on merge to main when the version changes
- PR title becomes the GitHub Release name
- CHANGELOG section becomes the GitHub Release body
- Docker build is chained automatically via workflow_call
- For hotfixes that don't need a release: don't bump the version
