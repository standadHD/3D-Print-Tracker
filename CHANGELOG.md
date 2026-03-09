# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [v0.4] - 2026-03-09

### Added
- **Eigene Spulenverwaltung** – vollständiges CRUD unabhängig von Spoolman
  - Hersteller (Vendors) anlegen, bearbeiten und löschen
  - Filamente mit Material, Farbe (inkl. Color Picker), Durchmesser, Dichte und Preis verwalten
  - Spulen mit Lagerort, Anfangs-/Restgewicht, Kaufdatum und Aktivstatus verwalten
- Neuer Tab **Spulenverwaltung** im Frontend mit drei Bereichen: Hersteller, Filamente, Spulen
- Neuer API-Endpoint-Block `/api/local/vendors`, `/api/local/filaments`, `/api/local/spools` mit vollständigem CRUD
- Spulenquelle beim Zuordnen zu Druckjobs wählbar: **Eigene Verwaltung** oder **Spoolman**
- Beim Sync wird als Fallback die aktive lokale Spule verwendet, wenn Spoolman nicht verbunden ist
- Fortschrittsbalken, Aktiv/Leer-Badges und Farbmarkierung auf lokalen Spulenkarten
- `/api/local/spools/locations` – Endpunkt für Lagerort-Autocomplete im Frontend
- `/api/local/spools/{id}/deduct` – manuellen Verbrauch von einer Spule abziehen
- Neue Datenbanktabellen: `filament_vendors`, `filaments`, `spools`

### Changed
- Spoolman bleibt **optional** – die App ist nun auch ohne Spoolman voll funktionsfähig
- Modal „Spule zuordnen" bei Druckjobs zeigt jetzt einen Umschalter zwischen lokaler Verwaltung und Spoolman
- `total_jobs_in_db` wird jetzt korrekt im `/api/status`-Endpoint zurückgegeben
- Spoolman-Tab in „Spulen (Spoolman)" umbenannt zur Unterscheidung von der eigenen Verwaltung

### Fixed
- Verbindungsstatus in den Einstellungen zeigte `last_sync` ohne Zeitstempel – jetzt `sync_time` aus dem Sync-Log

---

## [v0.3.1] - 2025-09-01

### Fixed
- Kostenneuberechnung nach manueller Änderung des Filamentverbrauchs

---

## [v0.3] - 2025-09-01

### Added
- Filamenttyp-Anzeige in der Joblisten-Übersicht
- Möglichkeit, den gemeldeten Filamentverbrauch manuell zu überschreiben wenn er als 0 gemeldet wird
- Filamenttyp-Filter in der Jobübersicht

### Fixed
- Manuell gesetztes Filamentgewicht wurde beim Sync überschrieben

---

## [v0.2.2] - 2025-09-01

### Added
- CFS-Mapping für Spulen mit automatischem Abgleich anhand des Druckjobs
- Spulen-Lagerort-Synchronisation mit Spoolman

### Fixed
- Spulen-Lagerort wurde nicht korrekt aus Spoolman übernommen

---

## [v0.2.1] - 2025-09-01

### Added
- Funktion zum nachträglichen Ändern der zugeordneten Spule bei Druckjobs

### Fixed
- Spulenpreis-Berechnung korrigiert
- Darstellungsfehler beim Wechseln der Spule (mehrere Iterationen, inkl. Firefox-spezifischer Fix)
- Spulenwechsel wurde nach Neustart des Containers nicht gespeichert

---

## [v0.2] - 2025-09-01

### Added
- Erstes getacktes Release
- Integration mit Moonraker für Druckjob-History
- Integration mit Spoolman für Filament- und Spulenverwaltung
- Kostenkalkulation pro Druckjob (Filament + Strom)
- Docker-Compose-basiertes Deployment

---

[Unreleased]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.4...HEAD
[v0.4]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.3.1...v0.4
[v0.3.1]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.3...v0.3.1
[v0.3]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2.2...v0.3
[v0.2.2]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2.1...v0.2.2
[v0.2.1]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2...v0.2.1
[v0.2]: https://github.com/standadHD/3D-Print-Tracker/releases/tag/v0.2
