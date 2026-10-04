# AI Studio — YouTube Watch Log

Purpose: track every YouTube video we watch for model/LoRA discovery so nothing is missed.
Each entry should list any models/LoRAs spotted; items worth adding go into `lora_catalog`
(source: `youtube`) with a link back to this log.

| Date watched | Video title | URL | Models/LoRAs spotted | Follow-up (added to catalog? y/n) |
|---|---|---|---|---|
| 2026-09-2x (backfill) | MiniMax H3 Actor Cloning Guide \| fal Agent Tutorial (Ref2VA + voice clone; "mush in the middle" duration lesson) | youtu.be/PtZdBMUVI04 | Ref2VA; voice clone; Singularity v1.3 INT8 + LMS LoRA (DualSampling lead source) | y — Singularity v1.3 INT8 + LMS LoRA confirmed missing on box; catalog follow-up |
| 2026-09-2x (backfill) | AI Samson — quality benchmark channel (276K subs) | youtube.com/@aisamsonreal | (channel — watch for model/LoRA mentions) | n — channel to keep monitoring |
| 2026-09-2x (backfill) | Reference batch w/ workflow JSON (DualSampling settings) | youtu.be/9oCppy1gZpo | DualSampling settings | n — settings reference |
| 2026-09-2x (backfill) | Reference batch w/ workflow JSON (DualSampling settings) | youtu.be/AykQHPVmG1w | DualSampling settings | n — settings reference |
| 2026-09-2x (backfill) | Reference batch w/ workflow JSON (DualSampling settings) | youtu.be/YR1vZN_jmWQ | DualSampling settings | n — settings reference |
| 2026-09-2x (backfill) | Reference batch w/ workflow JSON (DualSampling settings) | youtu.be/HJteqahyEKM | DualSampling settings | n — settings reference |

Conventions:
- Add a row for every video watched in an AI Studio / gen-stack research session.
- "Spotted" = any model, LoRA, checkpoint, or workflow mentioned as usable. Include the exact name as said/shown.
- If a spotted item is worth having, file it in `lora_catalog` (source `youtube`, `purchase_status` as applicable) and mark the follow-up column.
- Cross-check against the catalog when a video mentions something we think we already have — avoids dupes.
- Channels (not single videos) logged to monitor: youtube.com/@aisamsonreal (AI Samson).