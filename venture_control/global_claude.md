# PT Live Design — Global Claude Code Instructions

## Owner
Pete Thickett, PT Live Design, Lincoln UK.
All projects are part of the PT Live Design venture portfolio.

## Venture Control Dashboard

All projects belong to the Venture Control dashboard at FetaPit/Control_Room.
Project codes follow the pattern `26.XXX` (year prefix + 3-digit project number).

### Current projects

| Code  | Name              | Status      |
|-------|-------------------|-------------|
| 26.001 | Vault-It         | In progress |
| 26.002 | SUB-Terrainian   | In progress |
| 26.003 | Bauhaus 21       | Concept     |
| 26.004 | NFT Infinite Artwork | Concept  |
| 26.005 | Project Redshift | Live        |
| 26.006 | PeTe T           | In progress |
| 26.007 | PT Live Design (studio) | Live  |
| 26.008 | Live Fintech / FFHF | In progress |
| 26.009 | Daijishō         | Concept     |
| 26.010 | Plaza Futura     | Concept     |
| 26.011 | Shiba After Dark | Concept     |
| 26.012 | Career / FLA     | In progress |
| 26.013 | Vallum x Vice    | Scope TBC   |
| 26.014 | Infinite Value Glitch | In progress |
| 26.015 | PhoenixOS        | Scope TBC   |
| 26.016 | OP MASSIVE       | Scope TBC   |

### Rule: update pending.json when work is done

**At the end of any Claude Code session where a sprint, task, or Knox asset is completed:**

1. Write operations to `venture_control/pending.json` (project-local) OR
   `~/.claude/venture_control/pending.json` (global, works from any project)
2. The Stop hook auto-syncs to FetaPit/Control_Room — no manual action needed

**Operation format:**
```json
{
  "operations": [
    {
      "type": "update_project",
      "code": "26.002",
      "fields": { "readiness": 70, "status": "In progress", "touched": "2026-06-06", "streak": 2 }
    },
    {
      "type": "update_task",
      "task_code": "26.002.07",
      "fields": { "status": "Done" }
    },
    {
      "type": "add_knox",
      "entry": {
        "proj": "26.002",
        "ref": "26.002_BLD_CODE_ExampleSprint_20260606_v1.0_OFFICIAL",
        "title": "Sprint N description",
        "type": "Code", "cls": "OFFICIAL",
        "loc": "https://github.com/FetaPit/SUB-Terrainian",
        "note": "What was built."
      }
    }
  ]
}
```

Sync script: `~/SUB-Terrainian/tools/sync_dashboard.py`
Requires `CONTROL_ROOM_TOKEN` in `~/.env` or project `.env`.

## House style (all projects)

- Trading name: **PT Live Design**
- Never use: "Fyrra Studio", "fyrrastudio.com", "Bauhaus Twenty One"
- Full project names always — no abbreviations
- User-Agent on HTTP: `SubTerrainian/0.1 ( contact@ptliveddesign.example )`
