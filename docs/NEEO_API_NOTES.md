# NEEO Brain API Notes

## Status
Aktualisiert 2026-05-17 nach Live-Probe der Brain `192.168.40.10`. Alle hier dokumentierten Endpoints sind **verifiziert** ausser explizit markiert (vermutet).

## Test-Hardware-Klasse

```
Hardware:          NEEO Region EU, Revision 5
Firmware:          0.53.9-20180424 (April 2018, letzte vor Produkt-Einstellung)
Pro-Licensed:      false
Webserver:         nginx (proxiert intern auf Node.js)
```

Konkrete Brain-IPs/Hostnamen werden in den Code-Beispielen unten als
Platzhalter (`<brain-ip>`) gezeigt. Im Repo gibt es ausserdem
`docs/ARCHITECTURE.md` mit der Architektur-Sicht.

## Ports & Architektur

| Port | Zweck | Status |
|------|-------|--------|
| **3000** | REST-API + Socket.IO Event-Stream | verifiziert |
| **3200** | Statische EUI (Embedded UI, AngularJS-SPA) | verifiziert |
| 6336 | (vermutet) Brain-zu-Device-SDK fuer Reverse-Direction | nicht geprueft |

Beide Ports laufen ueber nginx als Proxy.

## Echtzeit-Push: Beide Mechanismen funktional - VERIFIZIERT 2026-05-17

Discovery-Run am 2026-05-17 hat beide Push-Mechanismen empirisch validiert. Siehe `discovery_results.md` fuer Rohdaten.

**Architektur-Entscheidung: Hybrid mit Forward Actions als Primaerweg.** Beide funktionieren, aber Forward Actions liefert reichhaltigere Payloads incl. Macro-Namen (z.B. "VOLUME UP"), Socket.IO liefert primaer State-Tracking.

### Forward Actions (Push-Webhook) - PRIMAERWEG

Brain pushed bei JEDER Aktion (Remote, App, API) an eine registrierte URL. Verifiziert: 17 Events in 60 Sekunden auf der Test-Brain, alle Aktionen incl. Macros + Recipe-Launch/Poweroff erfasst.

### Socket.IO Event-Subscription - SEKUNDAERER STATE-PFAD

Verifiziert NICHT sessiongebunden (Community-Theorie falsch fuer FW 0.53.9): Remote-Aktionen erzeugen Events. Aber Payload ist mager - bei `active-now-changed` nur ein Timestamp-Number ohne Recipe-Info. Bei `active-scenarios` Liste der aktiven Scenario-Keys. Eher nuetzlich fuer State-Sync als fuer Event-Detection.

### Warum Hybrid statt nur eins?

| Mechanismus | Was wir bekommen | Limitation |
|-------------|------------------|------------|
| Forward Actions | Vollstaendige Action-Info (action+device+room+recipe) bei JEDER Aktion | Nur eine URL pro Brain registrierbar → Forward-Chain noetig falls mehrere Consumer |
| Socket.IO `active-scenarios` | Liste aller aktiv laufenden Scenarios | Keine Action-Details |
| Socket.IO `active-now-changed` | Nur Timestamp (Marker) | Kein Payload mit Inhalt |

Mit Forward Actions allein haben wir alles was wir brauchen. Socket.IO koennte als doppelter Boden dienen falls Forward Actions Connectivity-Probleme hat. Aber V1.0 ist mit Forward Actions allein implementierbar.

**Architektur-Update v0.1:**
- Pflicht: Forward Actions Listener + Registrierung
- Optional/Spaeter: Socket.IO als State-Validator

## Socket.IO Event-Subscription (Option A Details)

Verifizierter Mechanismus, der von der EUI selbst genutzt wird.

### Connection-Details

```
Endpoint:     http://192.168.40.10:3000/socket.io/
Protokoll:    Engine.IO v3 (Socket.IO 2.x-Server)
Transports:   polling → upgrade auf websocket
Ping:         20000ms Interval, 10000ms Timeout
Namespace:    /  (Root-Default-Namespace)
```

### Initial-Handshake

```
GET /socket.io/?EIO=3&transport=polling
→ 97:0{"sid":"<SID>","upgrades":["websocket"],"pingInterval":20000,"pingTimeout":10000}2:40
```

Format-Decoder:
- `97:0...` ist Engine.IO Length-Prefixed Frame
- `0{...}` = OPEN-Paket mit Session-Info
- `2:40` = Socket.IO CONNECT-Paket fuer Default-Namespace

### Upgrade auf WebSocket

Nach dem Handshake:
```
ws://192.168.40.10:3000/socket.io/?EIO=3&transport=websocket&sid=<SID>
```

Empfohlen: WebSocket-Upgrade direkt, da Long-Polling den Brain unnoetig belastet und Session-Timeout-anfaellig ist.

### Verifizierte Socket.IO Events (aus EUI-Bundle extrahiert)

| Event | Bedeutung | Payload (vermutet) |
|-------|-----------|---------------------|
| `active-now-changed` | Aktives Recipe hat sich geaendert | Recipe-Key oder `null` |
| `active-scenario` | Aktives Scenario hat sich geaendert | Scenario-Info |
| `projectchanged` | Brain-Konfiguration geaendert (neue Recipes/Devices) | (vermutlich kein Payload, nur Trigger zum Refetch) |
| `fw:availabilitychanged` | Device-Erreichbarkeit geaendert | Device-Status |
| `disconnect` | Standard-Socket.IO Disconnect | n/a |

### Client-Library

Fuer Python: `python-socketio` (unterstuetzt EIO v3 mit `engineio_logger=True`). Konkret:

```python
import socketio
sio = socketio.AsyncClient(reconnection=True)

@sio.on("active-now-changed")
async def on_active(data):
    print("Active changed:", data)

@sio.on("projectchanged")
async def on_project(data):
    print("Project changed:", data)

await sio.connect("http://192.168.40.10:3000", transports=["websocket"])
```

`python-socketio` muss mit `version=3` Parameter konfiguriert sein wenn moderne Defaults nicht klappen.

## REST API

### Basis-URL
`http://192.168.40.10:3000`

### Verifizierte Endpoints (Read)

| Endpoint | Methode | Zweck | Status |
|----------|---------|-------|--------|
| `/systeminfo` | GET | Brain-Info (FW, IP, Uptime, Temperatur) | OK |
| `/v1/projects/home` | GET | **Root** - liefert komplettes Brain-Modell (rooms+devices+recipes+scenarios+buttons) | 200 |
| `/v1/projects/home/rooms` | GET | Alle Rooms + nested Devices + Macros | 200 |
| `/v1/projects/home/recipes` | GET | Alle Recipes/Activities | 200 |
| `/v1/projects/home/devices` | GET | Alle Devices Brain-weit | 200 |
| `/v1/forwardactions` | GET | Registrierte Forward-Action-Subscriber | 200 (`{}` leer) |
| `/events` | GET | **Event-LOG** (Historie der Recipe-Launches) | 200 |

### Verifizierte Endpoints (Trigger / Write)

Aus dem ioBroker-Adapter `magictom74/ioBroker.neeo` (main.ts) extrahiert - dort funktionierend eingesetzt:

| Endpoint | Methode | Zweck |
|----------|---------|-------|
| `/v1/projects/home/rooms/<roomKey>/recipes/<recipeKey>/execute` | GET | Recipe ausfuehren (Launch oder Poweroff je nach `type`-Feld des Recipe) |
| `/v1/projects/home/rooms/<roomKey>/devices/<deviceKey>/macros/<macroKey>/trigger` | GET | Macro (z.B. POWER ON, VOLUME UP) auf Device ausloesen |

**Wichtig:** Trigger-Calls sind GET-Requests (nicht POST), Recipe-Endpoint heisst `execute`, Macro-Endpoint `trigger`. Diese Convention ist NICHT in offizieller Doku, sondern empirisch aus dem ioBroker-Adapter validiert.

### `/v1/api/Recipes` - Convenience-Endpoint mit fertigen URLs

**Verifiziert auf Test-Brain (2026-05-17).** Liefert fertige URLs pro Recipe - kein manuelles URL-Bauen noetig:

```json
[
  {
    "type": "launch",
    "detail": {
      "devicename": "BluRay",
      "roomname": "Living",
      "model": "DBT-3313UD",
      "manufacturer": "Denon",
      "devicetype": "DVD"
    },
    "url": {
      "identify": "http://192.168.40.10:3000/v1/systeminfo/identbrain",
      "setPowerOn": "http://192.168.40.10:3000/v1/projects/home/rooms/<rk>/recipes/<rk>/execute",
      "setPowerOff": "http://192.168.40.10:3000/v1/projects/home/rooms/<rk>/recipes/<rk>/execute",
      "getPowerState": "http://192.168.40.10:3000/v1/projects/home/rooms/<rk>/recipes/<rk>/isactive"
    },
    "isCustom": false,
    "isPoweredOn": false,
    "uid": "...",
    "powerKey": "..."
  }
]
```

**Achtung:** Community-Erfahrung (openHAB, mqtt-neeo-bridge) zeigt: das `isPoweredOn`-Feld dieses Endpoints kann unter bestimmten Bedingungen veralten und falsche Werte zeigen. **Daher nicht als alleinige State-Quelle pollen.** Verwenden fuer initiale URLs/Listing, fuer State-Aenderungen Push-Mechanismen nutzen.

Recipes auf der Test-Brain (2026-05-17): BluRay, FM Radio (+ Z2/Z3), PlayStation, AV Receiver, TV.

### Nicht verifizierte Endpoints

| Endpoint | Zweck | Status |
|----------|-------|--------|
| `/v1/projects/home/activities` | (alternativer Pfad?) | 404 |
| `/v1/forwardactions/register` | Subscriber registrieren | 404 (falscher Pfad?) |
| `/v1/notifications` | Notifications? | 404 |
| `/ws`, `/socket.io/realtime` | alternative WS-Pfade | 404 |

### Recipe-Struktur (Beispiel aus realer Brain)

```json
{
  "key": "6332958412279644160",
  "type": "launch",
  "name": "AV Receiver",
  "icon": "default",
  "enabled": false,
  "dirty": true,
  "steps": [
    {
      "type": "action",
      "label": "Send \"POWER ON\" to \"AV Receiver\"",
      "deviceKey": "6332958388544077824",
      "deviceName": "AV Receiver",
      "componentName": "POWER ON"
    },
    { "type": "delay", "label": "Wait for 5 seconds", "delay": 5000, "smart": true },
    { "type": "volume", "label": "Use \"AV Receiver\" Volume", "deviceKey": "..." }
  ],
  "conditions": [],
  "trigger": { "type": "icon", "label": "When icon \"AV Receiver\" is pressed" },
  "roomKey": "6232364701641080832",
  "roomName": "Living",
  "scenarioKey": "6332958412103483392",
  "mainDeviceType": "AVRECEIVER",
  "isHiddenRecipe": true,
  "isCustom": false,
  "weight": 4
}
```

### /events Event-Log Struktur

Read-only historische Events, NICHT push:
```json
[
  {"timestamp":1779048594688,"value":"Poweroff recipe \"FM Radio\""},
  {"timestamp":1779048593850,"value":"Poweroff recipe \"FM Radio (Z3)\""},
  ...
]
```
Timestamps in Unix-Millisekunden. Wir nutzen das **nicht** fuer Echtzeit (dafuer Socket.IO), aber ggf. fuer Diagnostics/History-View.

## Beobachtete Daten der Test-Brain

### Rooms (1 Stueck)
- `Living`

### Devices (im Living-Room sichtbar)
- `AV Receiver` (Denon AVR-4520) - vollstaendige Command-Set vorhanden incl. INPUT BLUETOOTH, INPUT GAME, etc.

### Recipes (aus /events sichtbar)
- `TV`
- `FM Radio`
- `FM Radio (Z2)`
- `FM Radio (Z3)`
- `AV Receiver` (`isHiddenRecipe:true`)

## Forward Actions - VERIFIZIERTE API (2026-05-17)

### Registrierung

**Endpoint:** `POST /v1/forwardactions`

**Request-Body:**
```json
{
  "host": "192.168.40.30",
  "port": 8999,
  "path": "/neeo-callback"
}
```

**Response:** `{"success":true}` mit Status 200

Brain stuetzt **nur EINE aktive Registrierung** - jeder neue POST ersetzt die alte.

### Status pruefen

**Endpoint:** `GET /v1/forwardactions`

**Response:** `{"host":"...","port":...,"path":"..."}` - aktuelle Registrierung, oder `{"host":"","port":0,"path":""}` wenn keine aktiv.

### Unregistrieren

**Achtung:** DELETE wird NICHT unterstuetzt (404). Stattdessen:

**Endpoint:** `POST /v1/forwardactions`

**Body:** `{"host":"","port":0,"path":""}`

Damit wird die Registrierung geclearet (Brain wird beim naechsten Event nichts pushen).

### Alternative Pfade die auch 200 zurueckgeben

- `POST /forwardactions` (ohne /v1) - vermutlich Alias
- `POST /v1/forwardactions?url=<URL>` - Query-Param-Variante, untestbar fuer Empfang

Wir verwenden **`POST /v1/forwardactions` mit JSON-Body** als kanonische Methode.

### Payload-Schema der Brain-Pushes (VERIFIZIERT)

**Recipe Launch:**
```json
{
  "action": "launch",
  "device": "TV",
  "room": "Living",
  "recipe": "TV"
}
```

**Recipe Poweroff:**
```json
{
  "action": "poweroff",
  "device": "AV Receiver",
  "room": "Living",
  "recipe": "FM Radio"
}
```

**Macro / Button-Press auf Device:**
```json
{
  "action": "VOLUME UP",
  "device": "AV Receiver",
  "room": "Living"
}
```

**Channel-Button:**
```json
{
  "action": "CHANNEL_01",
  "device": "FM Radio",
  "room": "Living"
}
```

### Schema-Erkenntnisse

- `action`-Feld ist entweder:
  - `"launch"` oder `"poweroff"` (Recipe-Steuerung) - `recipe`-Feld ist dann gesetzt
  - Macro-Name in UPPERCASE (z.B. `"VOLUME UP"`, `"CHANNEL_01"`, `"CURSOR ENTER"`) - kein `recipe`-Feld
- `device`-Feld immer gesetzt
- `room`-Feld immer gesetzt
- `recipe`-Feld nur bei `launch`/`poweroff`
- KEIN `actionparameter`-Feld in der Praxis beobachtet (Community-Doku erwaehnte es)
- Content-Type: `application/json`
- HTTP-Methode: `POST`
- Brain pushed von seiner LAN-IP (`192.168.40.10`) ausgehend

### Volumen-Beobachtung

Schnelles Tasten-Druecken (VOLUME UP gehalten) erzeugt **mehrere Events pro Sekunde** - jedes einzelne Senden vom Remote ist ein eigener Push. Die HA-Integration muss das idempotent handlen oder rate-limiten.

### Lifecycle in HA-Integration

- `async_setup_entry`: 
  1. HomeAssistantView registrieren (eigener HTTP-Endpoint `/api/neeo/<entry_id>`)
  2. Brain POST `/v1/forwardactions` mit `{host: HA_IP, port: HA_PORT, path: /api/neeo/<entry_id>}`
- `async_unload_entry`:
  1. Brain POST `/v1/forwardactions` mit `{host:"", port:0, path:""}` (unregister)
  2. HomeAssistantView de-registrieren
- Brain-Reboot (Event `running` via Socket.IO oder Detection ueber GET `/systeminfo` uptime): Re-Register
- Coexistenz mit anderen Tools: Forward-Chain-Pattern (wir nehmen Push entgegen + leiten an Liste konfigurierbarer URLs weiter)

## Authentifizierung

**Keine** - alles offen im LAN. Brain hat im Werkszustand keinen Auth-Layer. Das ist OK fuer interne Netze, wir muessen aber:
- LAN-Trennung sicherstellen (Brain nicht ins WAN exponen)
- HA-Cloud-Access ueber HA-eigene Auth realisieren, nicht ueber Brain-Endpoint

## Open Questions / TODOs - ABGESCHLOSSEN nach Discovery 2026-05-17

1. ~~**Recipe-Trigger-Endpoint**~~ → GEKLAERT: `/rooms/<roomKey>/recipes/<recipeKey>/execute`
2. ~~**Macro-Trigger-Endpoint**~~ → GEKLAERT: `/rooms/<roomKey>/devices/<deviceKey>/macros/<macroKey>/trigger`
3. ~~**Active-Now Endpoint**~~ → Nicht noetig. Forward Actions pushed `action: launch/poweroff` mit `recipe`-Feld. Socket.IO `active-scenarios` zusaetzlich.
4. ~~**Button-Events von der Remote**~~ → GEKLAERT: kommen via Forward Actions als POST mit Action=Macro-Name (z.B. "VOLUME UP"), kein Recipe-Feld.
5. ~~**Socket.IO sessiongebunden?**~~ → GEKLAERT: NEIN. Remote-Aktionen werden auch ueber Socket.IO sichtbar (allerdings nur als state-tracking, nicht als action-event).
6. ~~**Forward Actions Endpoint**~~ → GEKLAERT: `POST /v1/forwardactions` mit `{host, port, path}` JSON.
7. ~~**Forward Actions Unregister**~~ → GEKLAERT: kein DELETE, sondern POST mit `{host:"", port:0, path:""}`.

Alle architektonisch relevanten Fragen sind beantwortet. Implementation kann starten.

## Gotchas

| Gotcha | Was tun |
|--------|---------|
| Engine.IO v3 (alt) - moderne socket.io-Clients sprechen v4 per Default | `python-socketio` explizit auf `engineio_options={"version": 3}` setzen oder direkten WebSocket-Client mit Custom-Decoder verwenden |
| Brain firmware aus 2018, nie wieder geupdatet | Verhalten ist stabil und vorhersagbar - aber keine modernen Features wie OAuth2/Auth |
| Session-Timeout bei Polling ohne Pings | WebSocket-Transport bevorzugen, nicht polling |
| Recipe-Keys sind grosse Strings (long-int) - bitte als Strings behandeln, nicht als Number | JSON-Parsing in JS interpretiert sonst falsch (Genauigkeitsverlust ueber 2^53) |
| `isHiddenRecipe:true` Recipes nicht in HA als Scene zeigen, aber als Service-Target zulassen | filter im Coordinator |
| EIO=4 (moderner Standard) wird vom Brain abgelehnt - immer EIO=3 verwenden | Konstante im Code |

## Reference-Repos

- **`magictom74/ioBroker.neeo`** (eigener vorgaengiger Adapter, lokal unter `D:\Code Development\divers\neeo`) - **GOLDQUELLE**:
  - Verifiziert API-Endpoint-Conventions (`/execute` fuer Recipes, `/trigger` fuer Macros, `/v1/projects/home` als Tree-Wurzel)
  - TypeScript-Type-Definitionen: `NeeoBrainModel`, `BrainRoom`, `BrainDevice`, `BrainRecipe`, `BrainMacro`, `BrainScenario` - portierbar 1:1 nach Python-Dataclasses
  - mDNS-Discovery via `bonjour` mit Service-Type `neeo` - aequivalent zu `_neeo._tcp.local` in Python `zeroconf`
  - **Was wir NICHT uebernehmen:** das 60s-Polling-Pattern (POLL_INTERVAL=60) zur isActive-State-Aktualisierung → ersetzt durch Socket.IO-Subscription
- `iobroker-community-adapters/ioBroker.neeo` (Community-Variante) - aelter, weniger relevant da eigener Adapter neuer
- `NEEOInc/neeo-sdk` - offizielles Brain SDK (Node.js), dokumentiert das Device-Protokoll (relevant fuer v0.4 Stretch)
- `Shepless/neeo-api` - alternative JS-Wrapper
