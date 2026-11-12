# John Guest Aura Home Assistant Integration

A Home Assistant custom integration for JG Aura heating thermostats.

It can reach the thermostats in two ways:

- **Local (recommended)**: through the **SAL01 USB stick** plugged into the Home Assistant host.
  No JG Aura gateway, no internet, no cloud account. Changes show up in Home Assistant within a
  second, because the thermostats push them.
- **Cloud**: through your JG Aura account, the JG Aura internet gateway and the Arrayent
  servers. JG Aura is winding down support, and this mode stops working when the servers are
  switched off.

## Features

- **Thermostat control**: target temperature and presets (Auto, High, Medium, Low, Party, Away, Frost)
- **Heating state**: shows whether each thermostat is calling for heat
- **Hot water control** (cloud only): a switch entity for hot water

## Installation

### HACS

Add this repository as a custom repository in HACS (category: Integration), install **JG Aura**,
then restart Home Assistant.

### Manual

Copy the `custom_components/jg_aura` folder into your Home Assistant `custom_components/`
directory and restart Home Assistant.

## Local setup with the SAL01 stick

The SAL01 is the small white USB stick (label "SAL01, 2.4 GHz") that plugs into the JG Aura
internet gateway (the square SALJG30 box).

1. Unplug the SAL01 from the gateway and plug it into the machine running Home Assistant.
   The gateway is not used in this mode. The heating keeps working while the stick is moved:
   the thermostats and the wiring centre work on their own.
2. If Home Assistant runs in Docker, pass the stick into the container, using its stable path:

   ```yaml
   services:
     homeassistant:
       devices:
         - /dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_XXXXXXXX-if00-port0
   ```

   (`ls /dev/serial/by-id/` on the host shows the exact name.) Pick this by-id path when setting
   up: unlike `/dev/ttyUSB0`, it stays the same across reboots and replugs. The port field also
   accepts a typed path.

   With the linuxserver.io image, Home Assistant only gets access to devices named
   `/dev/ttyUSB*` or `/dev/ttyACM*` inside the container, so give the stick such a name there
   and enter that name in the setup:

   ```yaml
       devices:
         - /dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_XXXXXXXX-if00-port0:/dev/ttyUSB-SAL01
   ```
3. Home Assistant usually discovers the stick by itself. Otherwise go to
   **Settings → Devices & Services → Add Integration → JG Aura** and pick **Local**.

The stick does not know thermostat names, so a new local entry shows them as "Thermostat bea0"
and so on; rename them in Home Assistant.

### Moving from the cloud to the stick

A cloud entry can be switched to the stick. Entities, names, automations and history are kept:

1. Move the SAL01 to the Home Assistant host (step 1 and 2 above).
2. **Settings → Devices & Services → JG Aura → ⋮ → Reconfigure**, and pick the stick's port.

Hot water control is only available through the cloud.

## Cloud setup

1. Go to **Settings → Devices & Services → Add Integration → JG Aura** and pick **Cloud**.
2. Enter your credentials:
   - **Email** and **Password**: your JG Aura account
   - **Host** (optional): defaults to `https://emea-salprod02-api.arrayent.com:8081/zdk/services/zamapi`
   - **Refresh Rate** (optional): polling interval in seconds (default: 30)
   - **Enable Hot Water**: whether to expose hot water control (default: on)

## Usage

Thermostats appear as `climate.<name>` entities: set the temperature, change presets and see the
room temperature and whether the thermostat is heating. Thermostats in Frost ignore target
temperature changes; pick another preset first.

Hot water (cloud only) appears as `switch.hot_water`.

## How it works

- **Local**: the integration talks to the SAL01 over its serial port; the protocol is
  documented in [docs/protocol.md](docs/protocol.md). Thermostats send
  a report on every change. Every 30 minutes the integration sets the thermostats' clocks to Home
  Assistant's local time, which also makes all of them report. Every 5 minutes it tells the
  thermostats a gateway is online, as the JG Aura gateway does, so their globe icon stays solid.
- **Cloud**: the integration polls the JG Aura HTTP/XML API.

## Troubleshooting

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.jg_aura: debug
```

- **"The SAL01 stick did not answer"**: check the stick is plugged in, passed into the container
  and not used by another program.
- **Stick unplugged**: the integration retries until it is back.
- **Diagnostics**: **Settings → Devices & Services → JG Aura → ⋮ → Download diagnostics** includes
  the last report of each thermostat.

## Development

Tests run in Docker:

```bash
docker build -t jg-aura-ha-test -f Dockerfile.test .
docker run --rm -v "$PWD":/src jg-aura-ha-test pytest
```

## Architecture

- `climate.py`: thermostat entities
- `switch.py`: hot water entity (cloud)
- `config_flow.py`: setup, USB discovery, reconfigure and reauth
- `jg_client.py`: JG Aura cloud API client
- `local_client.py`: SAL01 access with the same interface as `jg_client.py`
- `sal01/`: the SAL01 serial protocol (frames, payloads, asyncio client)
- `diagnostics.py`: diagnostics download
