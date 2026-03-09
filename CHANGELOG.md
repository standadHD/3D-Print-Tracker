# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [v0.3.1] - 2025-09-01

### Fixed
- Cost recalculation after manual filament usage update

---

## [v0.3] - 2025-09-01

### Added
- Filament type display in job list overview
- Possibility to manually override used filament weight when reported as zero
- Filament filter in job overview

### Fixed
- Override of filament weight being reset on sync

---

## [v0.2.2] - 2025-09-01

### Added
- CFS (Filament System) mapping for spools with automatic matching based on print job
- Spool location sync with Spoolman

### Fixed
- Spool location not being fetched correctly from Spoolman

---

## [v0.2.1] - 2025-09-01

### Added
- Function to change the assigned spool for existing print jobs

### Fixed
- Spool price calculation
- Display issue when changing spool (multiple iterations, including Firefox-specific fix)
- Spool change not being saved after container restart

---

## [v0.2] - 2025-09-01

### Added
- Initial tracked release
- Integration with Moonraker for print job data
- Integration with Spoolman for filament/spool management
- Cost calculation per print job
- Docker Compose based deployment

---

[Unreleased]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.3.1...HEAD
[v0.3.1]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.3...v0.3.1
[v0.3]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2.2...v0.3
[v0.2.2]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2.1...v0.2.2
[v0.2.1]: https://github.com/standadHD/3D-Print-Tracker/compare/v0.2...v0.2.1
[v0.2]: https://github.com/standadHD/3D-Print-Tracker/releases/tag/v0.2
