# Home Assistant FIXI Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Adds Fixi support to Home assistant. This integration requires [HACS](https://hacs.xyz).

## Installation

Recommended to be installed via [HACS](https://github.com/hacs/integration)

1. Go to HACS -> Integrations
2. [Add this repo to your HACS custom repositories](https://hacs.xyz/docs/faq/custom_repositories)
3. Search for Fixi and install.
4. Setup via YAML
    ```yaml
    sensor:
      - platform: fixi
        latitude: 50
        longitude: 5
        radius: 1000 # default
        count: 50 # default
    ```
5. Restart Home Assistant