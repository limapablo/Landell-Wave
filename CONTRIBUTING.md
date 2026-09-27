# Contributing

Contributions are welcome, especially fixes for location metadata, broken-stream handling, accessibility, and player compatibility.

## Local development

```bash
make test
make build
make serve
```

Open `http://localhost:8000`.

## Location quality

Radio Browser does not provide a universal city field. This project assigns a city only when a station has coordinates and the nearest GeoNames `cities1000` entry in the same country is within the configured distance threshold. Stations without a confident match remain under **Unknown city** rather than being guessed.

Data corrections should normally be made upstream in Radio Browser or GeoNames so every downstream user benefits.
