# Twitch Alert Overlay

Ein kleines OBS Browser-Overlay fuer Twitch-Alerts. Der Server nimmt einen
Webhook entgegen und spielt im Overlay die `.webm`-Datei ab, deren Name im
JSON-Body steht.

## Voraussetzungen

- Python 3.10 oder neuer fuer lokalen Start
- Docker mit Compose-Unterstuetzung fuer Betrieb hinter Traefik
- OBS Studio mit einer Browser-Quelle

## Lokaler Start

```bash
python3 server.py
```

Danach sind lokal diese URLs verfuegbar:

- Overlay fuer OBS: `http://localhost:3000/overlay/alerts`
- Webhook: `http://localhost:3000/overlay/alerts/webhook`
- Webhook, kompatibel: `http://localhost:3000/webhook`
- Healthcheck: `http://localhost:3000/overlay/alerts/health`
- Dateiliste: `http://localhost:3000/overlay/alerts/api/files`

Der lokale Port kann geaendert werden:

```bash
PORT=3010 python3 server.py
```

## Betrieb mit Docker Compose und Traefik

Docker Compose veroeffentlicht keinen Host-Port. Der Container haengt nur im
externen n8n-Netzwerk und wird von Traefik erreicht.

Kopiere die Beispielvariablen und passe sie an:

```bash
cp .env.example .env
```

Wichtige Variablen:

```dotenv
ALERT_OVERLAY_HOST=alerts.example.com
TRAEFIK_ENTRYPOINT=websecure
TRAEFIK_CERT_RESOLVER=letsencrypt
N8N_NETWORK=n8n-network
```

Start:

```bash
docker compose up --build -d
```

Extern routet Traefik nur diese Pfade:

```text
/overlay/alerts
/overlay/alerts/assets/*
/overlay/alerts/events
/overlay/alerts/media/*
/overlay/alerts/webhook
```

Nicht ueber Traefik geroutet werden zum Beispiel:

```text
/webhook
/health
/api/files
/overlay/alerts/health
/overlay/alerts/api/files
/overlay/chat
```

## WebM-Dateien hinzufuegen

Lege deine Alert-Dateien einfach in den Ordner `alerts/`.

Beispiel:

```text
alerts/
  follow.webm
  sub.webm
  raid.webm
```

Ein Neustart ist dafuer nicht noetig. Sobald eine Datei im Ordner liegt, kann
sie per Webhook abgespielt werden.

Videodateien in `alerts/` sind in `.gitignore` und `.dockerignore`
ausgeschlossen. Nur `alerts/.gitkeep` bleibt im Repository, damit der Ordner
vorhanden ist.

Wenn du lokal einen anderen Ordner verwenden willst:

```bash
ALERTS_DIR=/pfad/zu/deinen/alerts python3 server.py
```

Bei Docker Compose ist standardmaessig `./alerts:/app/alerts:ro` eingebunden.
Passe den Volume-Pfad in `docker-compose.yml` an, wenn du einen anderen lokalen
Alert-Ordner verwenden moechtest.

## Webhook ausloesen

Der Webhook akzeptiert `file`, `filename` oder `name`. Der Wert muss ein lokaler
Dateiname mit `.webm` sein, keine Pfade. Optional kannst du `message`, `text`
oder `caption` mitsenden. Wenn Text vorhanden ist, nutzt die WebM die oberen
zwei Drittel und die Message erscheint im unteren Drittel. Ohne Text bleibt die
bisherige Vollbild-Darstellung aktiv.

```bash
curl -X POST https://alerts.example.com/overlay/alerts/webhook \
  -H "Content-Type: application/json" \
  -d '{"file":"follow.webm","message":"Danke fuer deinen Follow!"}'
```

Lokal geht derselbe Request mit `http://localhost:3000`.

Antwort:

```json
{
  "ok": true,
  "alert": {
    "id": "b0d9f2f5-6b06-4a3b-a835-feb5dd0c2a9d",
    "file": "follow.webm",
    "url": "/overlay/alerts/media/follow.webm",
    "receivedAt": "2026-05-22T12:00:00Z",
    "message": "Danke fuer deinen Follow!"
  },
  "listeners": 1
}
```

Wenn mehrere Webhooks schnell hintereinander eintreffen, spielt das Overlay die
Videos nacheinander ab.

Falls du `{"ok": false, "error": "Endpoint not found."}` bekommst, pruefe, ob
der Request ein `POST` ist und auf `/overlay/alerts/webhook` zeigt. Ein `GET`
auf die Webhook-URL oder ein POST auf `/overlay/alerts` loest diesen Fehler aus.

## OBS einrichten

1. Neue Quelle hinzufuegen: `Browser`.
2. URL eintragen: `https://alerts.example.com/overlay/alerts`.
3. Breite/Hoehe auf Full-HD setzen: `1920x1080`.
4. `Browser-Quelle aktualisieren, wenn Szene aktiv wird` ist optional.
5. Audio kommt aus der Browser-Quelle. Stelle sicher, dass die Quelle in OBS
   nicht stummgeschaltet ist.

Nuetzliche Overlay-Parameter:

- `?volume=0.5` setzt die Lautstaerke auf 50 Prozent.
- `?fit=contain` zeigt das ganze Video verzerrungsfrei, ggf. mit transparenten Raendern.
- `?fit=cover` fuellt Full-HD verzerrungsfrei, kann aber Video-Raender abschneiden.
- `?debug=1` schreibt Debug-Infos in die Browser-Konsole, bleibt aber im Overlay unsichtbar.

Beispiel:

```text
https://alerts.example.com/overlay/alerts?volume=0.8&fit=contain
```

## Twitch/Webhook-Hinweis

Twitch selbst kann deinen lokalen Rechner nicht direkt erreichen. In der Praxis
wird der POST auf `/overlay/alerts/webhook` meist von einem Bot, Streamer.bot,
Mix It Up, n8n, einem eigenen Backend oder einem Tunnel wie Cloudflare
Tunnel/ngrok ausgeloest.
