---
name: patch-digest
description: Use when summarizing Dota 2 patch notes into a short Russian list of the main changes. Triggered for new patch announcements and attached patch notes files.
---

# Patch digest

The input is Dota 2 patch notes, usually in English, provided as an attached file or as text.

## Rules

- Write in Russian.
- If the provided patch-notes text is truncated, summarize what is available. Do not invent missing changes.
- Output ONLY the digest: 5-10 bullet points, each starting with "- ".
- Pick the most impactful changes: global/map changes, item changes, and significant hero buffs and nerfs.
- Do not list every change. Merge related changes and skip minor number tweaks.
- Prefer changes to popular heroes and items, new mechanics, and big buffs/nerfs that can shift the meta.
- Mention exact numbers when they are present (damage, cooldown, cost, duration and so on).
- Do not invent numbers, heroes, items, or changes. Use only the provided patch notes.
- No title, no preamble, no conclusion, no markdown headers, no code fences, no tables.
- Keep the whole answer under 3000 characters.
