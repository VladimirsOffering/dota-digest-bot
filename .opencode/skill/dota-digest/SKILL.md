---
name: dota-digest
description: Use when asked for a short Russian digest ("дайджест", "краткая выжимка") of Dota 2 materials gathered from several RSS sources. Turns raw headlines into a Discord-ready bullet list.
---

# Dota 2 digest

Turn raw headlines and snippets from several sources into one short Russian digest.

## Rules

- Write in Russian, neutral news tone.
- Choose the 5-8 MOST IMPORTANT and POPULAR stories from the candidates. Do not summarize everything that was provided.
- Output ONLY the digest: bullet points, each starting with "- ".
- Each bullet is 1-2 sentences: what happened and why it matters.
- End EVERY bullet with the source as a markdown link to the exact article, using the source name as the link text: `([Steam](https://...))`.
- Use only the source names and URLs given in the input. Never invent, shorten, or paraphrase links.
- If the same story appears in several sources, treat it as more important and merge it into one bullet, keeping the most informative source.
- Prioritize: patches and balance changes, heroes and items, tournaments and results, roster and transfer news, notable pro players and streamers, official Valve news.
- Skip rumors, clickbait, memes, clips, low-effort posts, and anything unrelated to Dota 2.
- Do not invent facts, numbers, dates, or quotes. If a detail is missing, omit it.
- No title, no preamble, no conclusion, no markdown headers, no code fences, no tables.
- Keep the whole answer under 3500 characters.

## Output example

- Вышел патч 7.39c: ослаблены несколько популярных героев ([Steam](https://example.com/news/1))
- Team Spirit выиграла крупный турнир, обыграв в финале ... ([Reddit r/DotA2](https://example.com/news/2))
