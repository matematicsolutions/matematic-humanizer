# matematic-humanizer

AI text has tells: inflated wording, filler, the rule of three, empty enthusiasm, chatbot
artefacts. This plugin removes them and leaves plain, precise prose, in three languages:

| Skill | Language | Language-specific layer |
|---|---|---|
| `humanizer-en` | English | English word lists and typography |
| `humanizer-pl` | Polish | Polish slop vocabulary, calques from English, Polish typography, 2026 spelling reform |
| `humanizer-pt` | Portuguese (pt-BR default, pt-PT on request) | gerundism, pronominal "mesmo", calques, variant mixing |

All three share one taxonomy, built on Wikipedia's "Signs of AI writing". Claude picks the
edition that matches the text. Each skill instructs Claude to rewrite wording and keep the
facts; review the result as you would any edit.

## House style is a default

Each edition ships one opinionated default: a single kind of dash (hyphen only) and a calm,
precise voice. If you give Claude your own style guide, a writing sample or a voice skill,
yours wins. The anti-slop patterns apply either way.

## Purpose

A quality pass for prose. Whether and how you disclose AI use stays your call; the skills
make the writing better and leave that decision to you.

## Install

In Claude Code:

```
/plugin marketplace add matematicsolutions/matematic-humanizer
/plugin install matematic-humanizer@matematic-humanizer
```

Single-skill zips, no plugin needed, are on the MateMatic Boutique:
[English](https://matematicsolutions.com/en/boutique/skills#skill-humanizer-en) ·
[Polish](https://matematicsolutions.com/boutique/skille#skill-humanizer-pl) ·
[Portuguese](https://matematicsolutions.com/pt/boutique/skills#skill-humanizer-pt)

## Data

The skills have no connectors and make no network calls of their own. They work on the
text in your conversation, which Claude processes the same way as any other message you
send it.

## Licence

MIT. Adapted from [blader/humanizer](https://github.com/blader/humanizer) (MIT); see
`NOTICE` for full attribution.
