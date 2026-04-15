# Korfbal Schedule — Home Assistant Custom Integration

Haalt het wedstrijdprogramma op van **mijn.korfbal.nl** (aangedreven door Sportlink/KNKV)
en biedt dit aan als een **Kalender** en **Sensoren** in Home Assistant.

---

## Wat doet het?

| Entity | Beschrijving |
|--------|-------------|
| `calendar.korfbal_<team>_wedstrijden` | Kalender met alle wedstrijden — werkt in de HA Agenda-kaart en met Google Calendar sync |
| `sensor.korfbal_<team>_volgende_wedstrijd` | Datum/tijd van de volgende wedstrijd (+ alle details als attributen) |
| `sensor.korfbal_<team>_aantal_wedstrijden` | Aantal aankomende wedstrijden |

---

## Installatie

### Stap 1 — Kopieer de bestanden

Kopieer de map `korfbal_schedule` naar je Home Assistant configuratiemap:

```
/config/custom_components/korfbal_schedule/
├── __init__.py
├── calendar.py
├── config_flow.py
├── coordinator.py
├── manifest.json
├── sensor.py
└── strings.json
```

Met HACS (aanbevolen via "Custom repository") of handmatig via SSH/Samba.

### Stap 2 — Herstart Home Assistant

```
Instellingen → Systeem → Herstart
```

### Stap 3 — Integratie toevoegen

1. Ga naar **Instellingen → Apparaten & Diensten → Integratie toevoegen**
2. Zoek op **Korfbal Schedule**
3. Vul in:
   - **Clubcode**: `NCX35C2`  ← uit jouw URL
   - **Teamcode**: `T1200100098`  ← uit jouw URL
   - **Teamnaam**: bijv. `Heren 1`
   - **Sportlink Client ID**: *(zie hieronder, optioneel maar aanbevolen)*

---

## Gegevensbronnen — twee strategieën

### Strategie A: Officiële Sportlink Club.Dataservice API (aanbevolen)

De meest betrouwbare methode. Vereist een **Client ID** van Sportlink Services.

**Hoe krijg je een Client ID?**
- Jouw korfbalvereniging moet **Club.Dataservice** hebben besteld bij Sportlink.
- Vraag de webmaster/secretaris van je vereniging om het Client ID.
- Of meld je zelf aan op: https://www.sportlink.nl/producten/club-dataservice/

**API endpoint die gebruikt wordt:**
```
GET https://data.sportlink.com/programma
  ?clientId=<JOUW_CLIENT_ID>
  &teamcode=T1200100098
  &aantaldagen=90
  &eigenwedstrijden=ja
```

### Strategie B: Mijn Korfbal SPA scraper (geen API key nodig)

Laat het `sportlink_client_id` veld leeg. De integratie probeert dan:

1. **JSON API** van de SPA intern: `https://mijn.korfbal.nl/api/v1/teams/{teamCode}/matches`
2. **HTML fallback**: zoekt naar bootstrapped JSON in de paginabron

> ⚠️ De SPA rendert client-side. Als de JSON API endpoint wijzigt of
> authenticatie vereist wordt, werkt alleen Strategie A nog betrouwbaar.

---

## Lovelace voorbeeldkaarten

### Agenda-kaart (ingebouwd)
```yaml
type: calendar
entities:
  - calendar.korfbal_heren_1_wedstrijden
initial_view: listWeek
```

### Volgende wedstrijd — markdown kaart
```yaml
type: markdown
title: Volgende Wedstrijd
content: |
  ## 🏐 {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'home_team') }}
     vs
  ## {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'away_team') }}

  📅 {{ states('sensor.korfbal_heren_1_volgende_wedstrijd') | as_datetime | as_local }}
  📍 {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'location') }}
  🏆 {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'competition') }}
```

### Entities kaart
```yaml
type: entities
title: Korfbal
entities:
  - sensor.korfbal_heren_1_volgende_wedstrijd
  - sensor.korfbal_heren_1_aantal_wedstrijden
```

---

## Automatie voorbeelden

### Herinnering dag van tevoren
```yaml
automation:
  - alias: "Korfbal morgen reminder"
    trigger:
      - platform: time
        at: "20:00:00"
    condition:
      - condition: template
        value_template: >
          {% set next = states('sensor.korfbal_heren_1_volgende_wedstrijd') | as_datetime %}
          {% set tomorrow = now() + timedelta(days=1) %}
          {{ next.date() == tomorrow.date() }}
    action:
      - service: notify.mobile_app_jouw_telefoon
        data:
          title: "🏐 Korfbal morgen!"
          message: >
            {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'home_team') }}
            vs {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'away_team') }}
            om {{ states('sensor.korfbal_heren_1_volgende_wedstrijd') | as_datetime | as_local | strftime('%H:%M') }}
            bij {{ state_attr('sensor.korfbal_heren_1_volgende_wedstrijd', 'location') }}
```

---

## Google Calendar sync

Als je de HA **Google Calendar** integratie hebt:
1. Voeg de `calendar.korfbal_*` entiteit toe in de Google Calendar config
2. Wedstrijden verschijnen automatisch in je Google Agenda

Of gebruik de ingebouwde HA Kalender — die is al zichtbaar na installatie.

---

## Vernieuwen

Gegevens worden elke **6 uur** automatisch ververst.
Handmatig vernieuwen: **Instellingen → Apparaten & Diensten → Korfbal Schedule → Vernieuwen**.

---

## Problemen oplossen

| Probleem | Oplossing |
|---------|-----------|
| Geen wedstrijden zichtbaar | Controleer club- en teamcode in de URL. Voer een Sportlink Client ID in voor betrouwbare data. |
| `UpdateFailed` in logs | Netwerk probleem of API wijziging. Controleer HA logs via `Instellingen → Systeem → Logboek`. |
| SPA scraper werkt niet | Gebruik de officiële Sportlink API (vraag Client ID bij jouw vereniging). |

Log level verhogen voor debug:
```yaml
# configuration.yaml
logger:
  logs:
    custom_components.korfbal_schedule: debug
```

---

## URL-structuur mijn.korfbal.nl

```
https://mijn.korfbal.nl/team/details/{CLUB_CODE}/{TEAM_CODE}/programma
                                       ^^^^^^^^^  ^^^^^^^^^^^^
                                       NCX35C2    T1200100098
```

Beide codes zijn zichtbaar in de URL van je teampagina.
