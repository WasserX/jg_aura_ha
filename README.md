# John Guest Aura Home Assistant integration
## Installation
Clone the repo and copy the contents of custom_components.
Add the following to your configuration.yaml

# John Guest Aura Home Assistant Integration

A Home Assistant custom integration for JG Aura thermostats and hot water control. Provides climate entities for thermostats and a switch entity for hot water with real-time state updates via cloud polling.

## Features

- **Thermostat Control**: Set temperature setpoints, change heating modes (Auto, High, Medium, Low, Party, Away, Frost)
- **Hot Water Control**: Turn hot water on/off with a switch entity
- **Real-time Updates**: Polling-based updates every 30 seconds (configurable)

## Installation

Copy the `custom_components/jg_aura` folder into your Home Assistant `custom_components/` directory

## Setup

The integration uses Home Assistant's config flow UI for setup (no YAML configuration required):

1. Go to **Settings → Devices & Services**
2. Click **Create Integration** (bottom right)
3. Search for **JGAura**
4. Enter your credentials:
   - **Email**: Your JG Aura account email
   - **Password**: Your JG Aura account password
   - **Host** (optional): Defaults to the official API endpoint `https://emea-salprod02-api.arrayent.com:8081/zdk/services/zamapi`. Override if using a different server.
   - **Refresh Rate** (optional): Polling interval in seconds (default: 30)
   - **Enable Hot Water**: Whether to expose hot water control (default: on)

## Usage

### Thermostats

Once configured, thermostats will appear as `climate.<name>` entities:

- Set temperature via the thermostat card
- Change preset modes (Auto, High, Medium, Low, Party, Away, Frost)
- View current temperature and heating state

### Hot Water

Hot water control appears as `switch.hot_water`:

- Turn on/off to control hot water heating

## How It Works

- **Data Flow**: The integration polls the JG Aura API every 30 seconds (configurable) to fetch thermostat and hot water status
- **API Communication**: Uses HTTP/XML endpoints for authentication and device state queries
- **State Changes**: When you change a setting (temperature, preset mode, hot water), the command is sent to the API and an immediate refresh is triggered to confirm the state change in Home Assistant
- **No External Dependencies**: Uses only Home Assistant and Python standard library

## Troubleshooting

### Enable Debug Logging

Add this to `configuration.yaml` to see detailed integration logs:

```yaml
logger:
  default: info
  logs:
    custom_components.jg_aura: debug
```

### State Not Updating

If entity state doesn't update after a change:
- Check the integration logs for API errors
- Verify your credentials are correct
- Ensure your JG Aura account can access the API from your Home Assistant location

### Integration Not Loading

Ensure you've restarted Home Assistant after adding the integration, or use the "Reload" option in **Settings → Devices & Services**.

## Architecture

- `climate.py`: Thermostat entity implementation
- `switch.py`: Hot water entity implementation  
- `config_flow.py`: Configuration UI
- `jg_client.py`: JG Aura API client (HTTP/XML parsing)
- `httpClient.py`: Low-level HTTP retry logic

Enjoy.
