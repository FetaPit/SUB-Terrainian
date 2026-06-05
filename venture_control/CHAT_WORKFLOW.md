# Venture Control — Chat & Projects workflow

This file explains how to keep the dashboard up to date from Claude.ai
chat and Claude Projects (not just Claude Code sessions).

---

## Claude.ai — Add to your Custom Instructions

Go to claude.ai → Settings → Custom Instructions and add the following:

---

**START COPY**

I am Pete Thickett, sole trader at PT Live Design, Lincoln UK.

I maintain a live Venture Control dashboard at:
https://fetapit.github.io/Control_Room/

It tracks 16 active ventures (code 26.001–26.016).

**At the end of any conversation where significant work is done**, output a
JSON block tagged `<!-- VENTURE_OPS -->` in this format:

```json
<!-- VENTURE_OPS -->
{
  "operations": [
    {
      "type": "update_project",
      "code": "26.XXX",
      "fields": { "readiness": N, "status": "...", "touched": "YYYY-MM-DD", "streak": N }
    },
    {
      "type": "update_task",
      "task_code": "26.XXX.NN",
      "fields": { "status": "Done" }
    },
    {
      "type": "add_knox",
      "entry": {
        "proj": "26.XXX",
        "ref": "26.XXX_TYPE_DOC_Title_YYYYMMDD_v1.0_OFFICIAL",
        "title": "Short title",
        "type": "Doc", "cls": "OFFICIAL",
        "loc": "location",
        "note": "What it is."
      }
    }
  ]
}
<!-- /VENTURE_OPS -->
```

Only output this block if something meaningful was completed or decided.
Match the project code to the relevant venture from my portfolio.

**END COPY**

---

## Applying a chat update (one command)

After a Claude chat session outputs a `<!-- VENTURE_OPS -->` block:

1. Copy just the JSON (between the tags, not the tags themselves)
2. Paste it into `~/SUB-Terrainian/venture_control/pending.json`
   replacing the `"operations": []` content
3. Run:
   ```bash
   python ~/SUB-Terrainian/tools/sync_dashboard.py
   ```

The dashboard updates within seconds.

---

## Alternative: paste directly to GitHub

If you don't want to use the command line:

1. Copy the JSON block from the chat
2. Go to: https://github.com/FetaPit/Control_Room
3. Click "Add file" → "Create new file"
4. Name it: `pending/YYYYMMDD_HHMM.json`
5. Paste the JSON content
6. Commit to main
7. GitHub Actions applies it to `index.html` automatically

---

## Claude Projects

For Claude Projects with code access, add the `global_claude.md` content
to the project instructions. The project can then write directly to
a `pending.json` file you include in the project context.

---

## Global Stop hook (Claude Code — all projects)

Copy `venture_control/global_settings.json` to `~/.claude/settings.json`
on your Termux device. This fires the sync script at the end of every
Claude Code session across ALL your projects — not just SUB-Terrainian.

**Note:** back up `~/.claude/settings.json` first if it already exists,
then merge the `hooks.Stop` entry into the existing file.
