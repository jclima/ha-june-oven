# Relayed frame excerpts

Each line is one WebSocket frame relayed by Project July's june-local server,
in receive order: `{"line": <line in the source capture>, "dir": "oven" |
"companion", "frame": <frame>}`. Frame data is verbatim. Signatures are blanked
and device IDs, device names, and targets are replaced with placeholders.

| File | Source capture | Shows |
| --- | --- | --- |
| `bake-timer-temperature.jsonl` | `relay-frames-20260922-g.jsonl` | A 350 °F bake started by a companion: preheat progress as a 0-100 percentage, a 10-minute timer (11006), a change to 325 °F (11005) that adds a step, then a cancel. |
| `oven-screen-proof.jsonl` | `relay-frames-20260922-p.jsonl` | An oven-clock 10018 dated 2022, a bake cancelled on the touchscreen, then a proof started on the touchscreen (plan 114, time progress, `cook_time_elapsed`) and an 11005 with `plan_id` 0 that the oven refused as `not-allowed`. |
| `preheat-complete.jsonl` | `factory-reset-20260923/relay-phase11-original-cert-20260923-191325.jsonl` | An 11005 below the cavity temperature finishing preheat: 10016 moves to `preheat_and_hold`, a 10015 repeats the earlier step, then 10012 `NOTIFICATION_PREHEAT_COMPLETE` and 10013 at 100%. |

# REST status responses

`rest-status.json` maps a case name to a `/1/messaging/device/{id}/status`
body. The cook plan is the proof plan (114) from `oven-screen-proof.jsonl` line
344.

| Case | Shows |
| --- | --- |
| `june_local_idle` | june-local's current idle response, verbatim: `ha_connection_state` "online" beside `connection_state` "connected", bare `device_state` beside wrapped `device_state_data`, and a null `cook_plan_data`. |
| `june_local_active` | The same aliases during a cook, with a bare `cook_plan` beside a wrapped `cook_plan_data`. |
| `cloud_active` | June's cloud shape: only `connection_state` "online", `device_state` and `cook_plan`, both wrapped in `{"data": ...}`. |
