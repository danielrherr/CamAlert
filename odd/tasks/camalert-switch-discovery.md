# CamAlert — Switch + Discovery implementation

Branch: main (local) · Status: in progress · Runner: `python3 -m unittest discover -s tests -v`

Implements the design in `docs/02_arquitectura_sistema.md` and `docs/05_integracion_switches.md`.

## Specs

- **S1** `src/switch_controller.py` provides `SmartSwitch(host, token, switch_id="1")` with `turn_on() -> bool`, `turn_off() -> bool`, `get_status() -> dict`, `set_switch_id(switch_id)`. Commands go to `POST {base_url}/control` with JSON `{"action": "on"|"off", "switch": switch_id}` and `Authorization: Bearer <token>`; status to `GET {base_url}/status`.
- **S2** Switch failures are safe: retries (2) then log and return `False` / raise `SwitchError` on `get_status`; never block the alert pipeline.
- **S3** `SwitchController(switch, threshold, min_interval_seconds)` activates only when `severity >= threshold`, and auto-deactivates after `min_interval_seconds`. Severity order is `low < medium < high < critical`.
- **S4** `src/config.py AlertConfig` gains `enable_switch`, `switch_host`, `switch_token`, `switch_id`, `switch_severity_threshold` (defaults: `false`, `""`, `""`, `"1"`, `"high"`), round-tripping through `to_dict`/`from_dict`.
- **S5** `src/alerts.py AlertManager` sends the switch channel when `enable_switch` is true, only for alerts at or above `switch_severity_threshold`. A switch failure never makes the alert fail (other channels still count), and it is reported in the channel result.
- **S6** Severity filtering must be ordinal, not lexicographic: `low < medium < high < critical`. `AlertResult` carries `error` when a channel fails.
- **S7** `src/discovery_manager.py` provides `DiscoveryManager` with `CameraIPState` tracking (`last_known_ip`, `discovery_timestamp`, `ip_stable`, `retry_count`) and `check_and_reconnect(cam_config, connect)` that tries the configured IP first, then network discovery matching **by MAC only**, updates `cam_config.host`, retries connect, and returns `(client, discovered)`; it never assigns an arbitrary discovered camera.
- **S8** `config/camalert.json` includes the five switch fields under `alerts`, `enable_switch` false by default.
- **S9** `main.py` compiles, imports `datetime`, wires `DiscoveryManager` instead of the inline stealing logic, and wires the switch controller through the alert config.

## Tasks

- T1 — S1, S2, S3: `src/switch_controller.py` + `tests/test_switch_controller.py` — done (RED 14 fails → GREEN)
- T2 — S4, S8: config fields + JSON + `tests/test_config_switch_fields.py` — done
- T3 — S5, S6: alerts integration + `tests/test_alerts_switch.py` — done
- T4 — S7: `src/discovery_manager.py` + `tests/test_discovery_manager.py` — done
- T5 — S9: main.py wiring — done (compile OK)

## Log

- L1 (verbatim): "retomemos el proyecto de camalert"
- Decision: initial commit `6ad1515` before implementation; then implement switch + discovery per the design docs.
- Discovery: `main.py` did not compile (`await` outside async function, `datetime` not imported); `alerts.py` compared severities lexicographically and referenced `AlertResult.error`, which did not exist.
- Evidence: `python3 -m unittest discover -s tests` → 32 tests OK; `python3 test_basic.py` OK; real-socket HTTP probe against a local fake switch passed (status/on/off/invalid-token).
- Behavior change accepted: severity filtering is now ordinal (a `critical` alert passes a `high` threshold; before it was skipped). Motion events now dispatch alerts from `main.py`.
- Pending: validation against real cameras and a real Norlink switch in the LAN.
