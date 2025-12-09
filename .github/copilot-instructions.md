**Big Picture**

This repository contains a Home Assistant custom integration for JG Aura thermostats and hot water control. The integration lives under `custom_components/jg_aura` and provides two platforms:

- **Climate**: `custom_components/jg_aura/climate.py` — exposes thermostats as `ClimateEntity` instances.
- **Switch**: `custom_components/jg_aura/switch.py` — exposes hot water as a `SwitchEntity`.

The integration is a modern config-entry-based cloud-polling integration: `jg_client.JGClient` talks to the vendor HTTP/XML API and returns small domain objects (`gateway.Gateway`, `thermostat.Thermostat`, `hotwater.HotWater`). Entities obtain updates via `DataUpdateCoordinator` patterns.

**Where to look**
- `custom_components/jg_aura/manifest.json`: integration metadata (`domain`, `iot_class`, `config_flow: true`).
- `custom_components/jg_aura/__init__.py`: config entry setup (`async_setup_entry`, `async_unload_entry`). No YAML schema needed.
- `custom_components/jg_aura/config_flow.py`: user-facing config flow for setup UI with credential validation. Host is optional with default API endpoint.
- `custom_components/jg_aura/strings.json`: user-facing error messages and field labels for config flow.
- `custom_components/jg_aura/const.py`: domain and config key constants.
- `custom_components/jg_aura/jg_client.py`: central HTTP/XML parsing, authentication, and device extraction logic.
- `custom_components/jg_aura/httpClient.py`: low-level async http helpers with retry logic (uses `await asyncio.sleep`).
- `custom_components/jg_aura/climate.py` and `switch.py`: modern `async_setup_entry()` platform implementations using `DataUpdateCoordinator`.

**Config / How to run locally**
- Add the `jg_aura` folder into Home Assistant `custom_components/` directory (or symlink).
- **Recommended**: Use UI config flow (Settings > Devices & Services > Create Integration) to add JGAura.
- Host field is optional and defaults to `https://emea-salprod02-api.arrayent.com:8081/zdk/services/zamapi`.
- Credentials are validated at setup time: invalid email/password shows an error in the UI instead of failing silently.
- YAML configuration is no longer required; integration is now config-flow-only.

**Project-specific patterns & conventions**
- Domain constant: `DOMAIN = "jg_aura"` (defined in `const.py` and imported across files).
- Config keys: `CONF_REFRESH_RATE`, `CONF_ENABLE_HOT_WATER` are defined in `const.py` for consistency.
- Unique IDs: Entities set `_attr_unique_id` using the device id (e.g. `"jg_aura-<id>"` for thermostats and `"jg_aura-hotwater-<id>"` for hot water).
- Config entry data flow: `hass.data[DOMAIN][entry.entry_id]` stores config data; platforms extract it in `async_setup_entry()`.
- Both platforms use `DataUpdateCoordinator` with coordinator listeners for entity state updates.
- **Immediate state refresh on change**: State-changing methods (`async_set_preset_mode`, `async_set_temperature`, `async_turn_on/off`) now call `async_write_ha_state()` immediately to reflect optimistic state, then trigger `coordinator.async_request_refresh()` to confirm the change was registered on the API.

**Integration & API notes (important when editing `jg_client.py`)**
- `JGClient` implements a lightweight login flow and then calls endpoints like `/userLogin`, `/getDeviceList`, `/getDeviceAttributesWithValues`, and `/setMultiDeviceAttributes2`. Responses are XML parsed with `xml.etree.ElementTree`.
- Credentials: the password is MD5 hashed before being included in the login URL (`hashlib.md5`). Timestamp strings are generated with `datetime.now().timestamp()` and dots removed.
- The API encodes state in compact custom payloads; `jg_client.__extractThermostats` and `__extractHotWater` contain the bit/byte decoding logic — change carefully and add tests if altering parsing.

**Implementation details & gotchas (FIXED)**
- ✅ **FIXED**: `httpClient.callUrlWithRetry` now uses `await asyncio.sleep(1)` instead of blocking `time.sleep`. This prevents blocking Home Assistant's event loop during retries.
- ✅ **FIXED**: `switch.py`'s `update_entities` callback now calls `async_write_ha_state()` to immediately reflect state updates.
- ✅ **FIXED**: State-changing operations (`async_set_preset_mode`, `async_set_temperature`, `async_turn_on/off`) now include a 2-second delay before coordinator refresh. This gives the JG Aura API time to process the change before querying, eliminating the race condition where stale values were returned.
- No external `requirements` in `manifest.json`; all dependencies are standard library or Home Assistant provided.
- Integration is now config-flow-only; no YAML schema in `__init__.py`.

**Testing, debugging, and quick checks**
- To enable extra debug logging for development, set this in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.jg_aura: debug
```

- For iterative development:
  - Edit code under `custom_components/jg_aura` in your HA config directory.
  - Reload integrations or restart Home Assistant to pick up changes.

**What to change carefully / where to add tests**
- `jg_client.py` parsing: add unit tests for `__extractThermostats` and `__extractHotWater` using representative XML samples before refactoring.

---
Updated to reflect modern config-entry-based architecture (v2.0.0+). Uses `async_setup_entry()` and `config_flow.py`. YAML config is deprecated. HTTP retry logic uses async sleep, entity state updates are immediate with confirmed refresh.
