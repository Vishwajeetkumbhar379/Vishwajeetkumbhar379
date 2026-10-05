# LinkedIn carousel pipeline

Turn one topic idea into a **carousel PDF** and a **caption**, ready to post.
Nothing here ever posts for you. You always look first, then post by hand.

```
topic idea  ->  slides + caption (a small JSON file)  ->  PDF + caption.txt  ->  you approve  ->  you post
```

## What you get

- `carousel.pdf`: 9 slides, 1080 x 1350 (the 4:5 size LinkedIn likes)
- `caption.txt`: the text to paste above the PDF
- `preview/slide-1.png ...`: pictures of each slide, easy to flick through on a phone

See a finished one in `examples/llm-judge-bias/`.

## The look (locked)

Warm paper background, serif headlines, tinted cards (purple `#F5F4FF`, teal `#F0FBF6`,
coral `#FEF6F3`), accent `#7F77DD`, hairline 0.5px borders, a badge on every card,
a pill slide counter top-right, your handle top-left. No chat bar.
All colours live in one file: `theme.css`.

## Make a new carousel (works from an iPad, all in the cloud)

1. Open this repo in Claude Code on the web.
2. Say: **"New carousel about: <your topic>."** Claude writes `content/<name>.json`
   (rare, high-signal AI x marketing only, no generic tips).
3. Claude runs:
   ```bash
   python3 linkedin/build.py linkedin/content/<name>.json
   ```
4. The build **checks the content first** and stops with a plain message if something is off
   (too many words on a slide, AI-sounding words, a missing "save this", more than one question,
   a leftover `{{placeholder}}`, or anything that looks like a secret).
5. Open `linkedin/out/<name>/carousel.pdf` and `caption.txt`. Say what to change, or say **approve**.
6. Post by hand: LinkedIn > Start a post > add document > pick the PDF > paste the caption.

## Settings (all optional, none are secret)

| What | How |
|---|---|
| Your handle (shown top-left) | edit `config.json`, or set the variable `LINKEDIN_HANDLE` |
| Where Chromium is, if not found automatically | set the variable `CHROME_PATH` |

## Posting with Zapier

A Zapier LinkedIn connection can post **text and a link only**. It cannot upload a PDF,
so the carousel itself is always posted by hand. Claude will only use Zapier to post a
text version if you say so, and only after you approve the exact words.
You do not need a webhook URL for this. **Never paste passwords, API keys, tokens or webhook
URLs into any file in this repo, it is public.** If you ever add one, keep it in the
cloud environment's secret settings and read it from an environment variable.

## Files

```
linkedin/
  build.py        the builder (Python standard library only)
  theme.css       the locked style
  config.json     your handle
  content/        one JSON file per topic
  fonts/          Inter + Newsreader (open licence), so the PDF looks the same everywhere
  examples/       finished carousels you can open and look at
  tests/          run:  python3 -m unittest discover -s linkedin/tests
  out/            build output (not saved to git)
```

## Slide types for the JSON

`cover`, `stake`, `point` (with optional `demo` rows and a `fix` box), `stack` (arrow list),
`recap` (two-column rows), `cta`. Keep headlines to 8 words or fewer (cover: 6), and
each text block short. Slides alternate tints automatically, or set `"tint"` yourself.
