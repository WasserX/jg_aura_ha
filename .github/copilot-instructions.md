**Big Picture**

This repository contains a Home Assistant custom integration for JG Aura heating thermostats and hot water. The integration lives under `custom_components/jg_aura` and provides two platforms:

- **Climate**: `climate.py` exposes thermostats as `ClimateEntity` instances.
- **Switch**: `switch.py` exposes hot water as a `SwitchEntity` (cloud only).

A config entry reaches the thermostats in one of two ways, chosen by `CONF_CONNECTION` in the entry data (entries without the key are cloud):

- **Local**: `local_client.LocalClient` talks to the SAL01 USB stick through the `sal01/` package (local push).
- **Cloud**: `jg_client.JGClient` talks to the vendor HTTP/XML API (polling).

Both clients return the same small domain objects (`gateway.Gateway`, `thermostat.Thermostat`, `hotwater.HotWater`) and expose the same methods, so the entities do not care which one they use. Entities get updates through a `DataUpdateCoordinator`; in local mode the stick's reports are pushed into it with `async_set_updated_data`.

**Where to look**
- `manifest.json`: integration metadata, requirements and the USB matcher for the stick.
- `__init__.py`: config entry setup and unload; picks the client and the platforms.
- `config_flow.py`: setup menu (local or cloud), USB discovery, reconfigure (switch an entry to a stick) and reauth.
- `translations/en.json`: UI strings for the config flow.
- `const.py`: domain and config key constants.
- `local_client.py`: SAL01 startup, periodic clock sync and commands.
- `sal01/`: the SAL01 serial protocol (frames, payloads, asyncio client, debug CLI). It does not import Home Assistant. The protocol is documented in `docs/protocol.md`.
- `jg_client.py` and `http_client.py`: cloud login, XML parsing and requests with retries.
- `diagnostics.py`: diagnostics download, with credentials redacted.

**Project-specific patterns & conventions**
- Domain constant: `DOMAIN = "jg_aura"` (in `const.py`).
- Unique IDs: thermostats use `jg_aura_<cloud id>`. The cloud id is the thermostat's radio address with its bytes swapped, so local and cloud entries produce the same entities.
- The client lives in `entry.runtime_data`.
- After a command, entities write the expected state at once and then ask the coordinator to refresh after the client's `refresh_delay` (the cloud needs time to apply changes; the stick does not).

**SAL01 gotchas**
- The stick needs RTS on and DTR off at 115200 8N1.
- Every frame from the stick must be acknowledged, or it is resent and reporting stops.
- The stick ignores a request whose sequence number or command counter repeats a recent one, so counters start at random values.
- Thermostats blink their globe icon unless a gateway sends `A° 1` every few minutes; `LocalClient.maintain()` does it (with the 30-minute clock sync) on its own timer, because pushed reports reset the coordinator's poll timer.

**Testing and debugging**
- Tests run in Docker:

```bash
docker build -t jg-aura-ha-test -f Dockerfile.test .
docker run --rm -v "$PWD":/src jg-aura-ha-test pytest
```

- `tests/sal01/` covers the protocol with captured frames; `tests/test_local.py` and `tests/test_config_flow.py` cover the Home Assistant side with a fake stick.
- Debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.jg_aura: debug
```
