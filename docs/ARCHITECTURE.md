# Architektur: HA-Integration NEEO

## Grundprinzip

```
┌─────────────────────────────────────────────────────────────┐
│                     NEEO Brain (Master)                      │
│                  TBD-IP:3000 (REST-API)                      │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  Recipes /  │  │  Devices     │  │  System             │ │
│  │  Activities │  │              │  │                     │ │
│  │             │  │  - TV        │  │  - System-Info      │ │
│  │ - TV ein    │  │  - AVR       │  │  - Rooms            │ │
│  │ - Watch     │  │  - Apple TV  │  │  - Connected-State  │ │
│  │ - Listen    │  │  - Hue       │  │                     │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│                                                              │
│         REST + mDNS-Discovery + Forward-Actions             │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
            │ HTTP Commands                       │ Forward-Actions
            │ (Brain antwortet)                   │ (Brain pushed)
            ↓                                     ↓
┌─────────────────────────────────────────────────────────────┐
│                    pyneeo (Library)                          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  Client     │  │  Discovery   │  │  Listener           │ │
│  │             │  │              │  │                     │ │
│  │  - Recipes  │  │  - mDNS-Scan │  │  - HTTP-Server      │ │
│  │  - Devices  │  │  - Brain-ID  │  │    fuer Brain-Pushs │ │
│  │  - Trigger  │  │  - Health    │  │  - Event-Dispatch   │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Python async API + Callbacks
                           ↓
┌─────────────────────────────────────────────────────────────┐
│         custom_components/neeo (HA Integration)              │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  Setup      │  │  Entities    │  │  Services           │ │
│  │             │  │              │  │                     │ │
│  │  - __init__ │  │  - Scene     │  │  - activate_recipe  │ │
│  │  - config_  │  │    (Recipes) │  │  - deactivate_recipe│ │
│  │    flow     │  │  - Sensor    │  │                     │ │
│  │  - coord-   │  │    (Active)  │  │                     │ │
│  │    inator   │  │  - BinSensor │  │                     │ │
│  │             │  │    (Online)  │  │                     │ │
│  │             │  │  - Event     │  │                     │ │
│  │             │  │    (Buttons) │  │                     │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              Home Assistant Core / Frontend                  │
└─────────────────────────────────────────────────────────────┘
```

## Schichten-Trennung

### Library `pyneeo/`

Reines API-Wrapping, **null HA-Abhaengigkeit**:
- `client.py` - HTTPClient (httpx), Connection-Management
- `discovery.py` - mDNS-Scanner via zeroconf
- `recipe.py` - Recipe-Modell + Trigger-Methoden
- `device.py` - NEEO-Device-Modell
- `listener.py` - HTTP-Server fuer Forward-Actions-Callbacks
- `exceptions.py` - NEEOError, NEEONotFoundError, NEEOTimeout

Library ist **standalone testbar** und koennte fuer andere Python-Projekte verwendet werden.

### Integration `custom_components/neeo/`

HA-spezifischer Glue-Code:
- `__init__.py` - Setup-Logik, Hub-Klasse
- `config_flow.py` - Auto-Discovery + manuelle IP-Eingabe
- `coordinator.py` - DataUpdateCoordinator (kombiniert API-Polling + Push-Events)
- `manifest.json` - Metadaten + Dependencies
- `const.py` - DOMAIN, DEFAULT_PORT, Event-Names
- `scene.py` - Recipes als Scene-Entities
- `sensor.py` - Active-Recipe, Online-Status
- `binary_sensor.py` - Brain-Reachable
- `event.py` - Button-Events
- `services.yaml`
- `strings.json` + `translations/`

## Event-Flow im Detail

### Recipe ausloesen (HA → NEEO)

```
User ruft Scene auf in HA
    → scene.async_activate()
    → Integration → pyneeo.activate_recipe(recipe_id)
    → HTTP POST http://<brain>:3000/v1/projects/home/recipes/<id>/on
    → Brain fuehrt Recipe aus (TV ein, AVR ein, Source umschalten, ...)
    → HA Scene-Entity state = "active"
```

### Recipe-Aktivierung via NEEO Remote (NEEO → HA)

```
User drueckt physisch Knopf auf Remote
    → Brain startet Recipe
    → Brain ruft konfigurierten Forward-Action-Endpoint auf: POST http://<HA-IP>:<NEEO-Listener-Port>/...
    → pyneeo.Listener empfaengt → Event-Dispatcher
    → Coordinator updated active-recipe-Sensor
    → HA-Event `neeo_recipe_activated` wird gefeuert
```

Setup-Voraussetzung: Forward-Action-URL muss einmalig im NEEO-Brain registriert werden (via API oder NEEO-App).

### Button-Drueckung (NEEO → HA)

```
User drueckt Custom-Button auf NEEO Remote (z.B. fuer Hue-Steuerung)
    → Brain pushed → POST /forwardactions an HA
    → Listener → Event-Dispatcher
    → HA-Event `neeo_button_pressed` mit Properties:
        device_id, button_name, action_parameter
    → User-Automations koennen darauf reagieren
```

## Discovery + Setup-Flow

```
HA Start oder Add-Integration
  → ConfigFlow
  → Optional: mDNS-Scan (zeroconf) fuer _neeo._tcp.local
  → Auto-Discovery zeigt gefundenes Brain (Name, IP, Port)
  → User waehlt aus / gibt IP manuell ein
  → Connection-Test (GET /systeminfo)
  → ConfigEntry gespeichert
  → __init__.async_setup_entry()
  → Brain-Init: Recipes/Rooms/Devices laden
  → Forward-Actions-Endpoint registrieren beim Brain (falls Push aktiv)
  → Platform-Forwards
  → Listener-Server starten (HTTP auf eigener Port, Default 8124)
```

## Forward Actions (Primaerer Mechanismus - VERIFIZIERT 2026-05-17)

Brain pushed bei jeder Aktion via HTTP-POST an eine registrierte URL.

### Registrierung beim Setup

```python
async def register_forward_actions(client, host, port, path):
    body = {"host": host, "port": port, "path": path}
    response = await client.post(
        f"http://{brain_ip}:3000/v1/forwardactions",
        json=body,
    )
    # response: {"success": true}
```

### Unregistrierung beim Teardown

```python
async def unregister_forward_actions(client):
    body = {"host": "", "port": 0, "path": ""}
    await client.post(
        f"http://{brain_ip}:3000/v1/forwardactions",
        json=body,
    )
```

Wichtig: DELETE wird NICHT unterstuetzt. Stattdessen leerer POST clearet die Registrierung.

### HomeAssistantView

```python
class NeeoForwardActionsView(HomeAssistantView):
    requires_auth = False  # Brain sendet kein HA-Token
    url = "/api/neeo/{entry_id}"
    name = "api:neeo"

    async def post(self, request, entry_id):
        data = await request.json()
        # data: {"action": "launch"|"poweroff"|"<MACRO_NAME>", "device": "...", "room": "...", "recipe"?: "..."}
        self.hass.async_create_task(self._dispatch(entry_id, data))
        # Forward-Chain: an weitere konfigurierbare Consumer weiterreichen
        return self.json({"status": "ok"})
```

### Payload-Erkennung

| `action`-Wert | Bedeutung | Zusaetzliche Felder |
|---------------|-----------|----------------------|
| `"launch"` | Recipe wurde gestartet | `recipe` Pflicht |
| `"poweroff"` | Recipe wurde beendet | `recipe` Pflicht |
| UPPERCASE-String | Macro/Button auf Device | nur `device` + `room` |

### Forward-Chain (Multi-Consumer)

Brain hat eine **Single-URL-Limit** - jede Re-Registrierung ueberschreibt die vorige. Falls neben HA noch andere Tools Forward Actions empfangen sollen, baut HA eine **Forward-Chain**: HA empfaengt → leitet an Liste konfigurierbarer URLs weiter. Pattern von openHAB NEEO Binding uebernommen.

```python
async def _forward_to_chain(data: dict, chain: list[str]):
    async with httpx.AsyncClient() as client:
        for url in chain:
            try:
                await client.post(url, json=data, timeout=5.0)
            except Exception as e:
                _LOGGER.debug(f"Forward to {url} failed: {e}")
```

## Socket.IO (Optionaler Sekundaer-Pfad)

Verfuegbar als ergaenzende State-Quelle. Empirisch nicht-sessiongebunden, aber Payloads sind mager (nur Timestamps + Scenario-Keys ohne Detail-Info). Nicht-Pflicht fuer v0.1.

Verifizierte Events:
- `active-now-changed` → `[<unix_ms_timestamp>]`
- `active-scenarios` → `{"activeScenarioKeys": ["<key>", ...]}` oder `[]`

Setup-Skizze fuer v0.2+ falls noetig:
```python
sio = socketio.AsyncClient(reconnection=True)

@sio.on("active-scenarios")
async def on_active_scenarios(data):
    active_keys = data.get("activeScenarioKeys", [])
    # State-Sync: alle Recipes durchgehen, deren Scenario aktiv ist → on
    ...

await sio.connect("http://192.168.40.10:3000", transports=["websocket"])
```

`python-socketio==4.x` (nicht 5.x) ist Pflicht - Brain spricht Engine.IO v3.

## Reconnect / Resilience

| Szenario | Strategy |
|----------|----------|
| Brain nicht erreichbar (Network-Fehler) | Binary-Sensor on `off`, Retry-Connect Socket.IO mit Exponential-Backoff (max 60s) |
| Brain-Reboot | mDNS-Reentdeckung, Connection-Test, Socket.IO-Reconnect (gleiche Subscription wird automatisch erneuert) |
| Socket.IO-Disconnect | Sofort reconnect, kein Fallback auf Polling |
| Cert-Probleme | Brain hat im LAN typ. kein TLS, fuer Reverse-Setup ggf. eigene Cert-Generierung |

**Hartes Prinzip:** Wenn Socket.IO ausfaellt → reconnecten, NICHT auf Polling ausweichen. Lieber kurzzeitig "stale state" als Polling-Overhead auf der schwachen Brain-Hardware.

## Tests-Strategie

- **Unit-Tests** (pyneeo): Mock-HTTPClient, mDNS-Mock, isolierte Modell-Tests
- **Integration-Tests** (pyneeo): VCR-Recordings von echten Brain-Responses
- **HA-Integration-Tests** (custom_components): pytest-homeassistant-custom-component
- **End-to-End**: gegen echte Brain im LAN (Test-Phase)

## Reverse-Direction (v0.4 Stretch - HA als NEEO-Device)

Optional, fuer "NEEO Remote steuert HA-Lichter direkt":

```
HA-Integration registriert sich beim Brain als "device":
- HTTP-Server auf eigenem Port
- Implementiert NEEO-Device-SDK-Protokoll
- Stellt HA-Entities (Lichter, Szenen, Media-Player) als NEEO-Capabilities zur Verfuegung
- Brain entdeckt und integriert sie ins UI des Remote

NEEO Remote bedient HA-Entities:
- User wischt zur HA-Light-Seite auf Remote
- Drueckt Slider
- Brain ruft unser Device-Endpoint
- Wir aendern die HA-Entity
- Brain zeigt neuen State auf Remote
```

Komplex (~ 2-3 Wochen extra). NICHT in v0.1-0.3 enthalten.

Reference: https://github.com/NEEOInc/neeo-sdk - dokumentiert das Device-Protokoll fuer Eigenentwicklungen.

## Distribution

- **GitHub-Repo:** `homeassistant-neeo` (Mono-Repo, magictom74/)
- **HACS:** `hacs.json` im Root, integration-Type
- **PyPI:** `pyneeo` separat publishbar (optional)
- **HA Brand:** falls Submission an HA Core
