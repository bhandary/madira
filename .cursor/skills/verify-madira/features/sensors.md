# Sensors

Sensors registers a probe on a storage zone and accepts a CSV of readings. A reading outside the zone band becomes an excursion, and Tonight shows it with the license reminder.

## Sub-features

- `sensor-create` registers a probe and shows its secret once.
- `sensor-csv` previews a reading and applies it.
- `sensor-tonight` lists the excursion and the seeded reminder on `/`.

## How to get to it (user POV)

- Choose `Sensors` in the sidebar or in `More`, or open `http://127.0.0.1:3000/sensors`.
- Source: `frontend/src/app/sensors/page.tsx`, Tonight lines in `frontend/src/app/page.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. `[data-testid=sensor-create]` is enabled.

- **Register.** Open `/sensors`. The heading is `Sensors`. Fill the Name field with `Cellar probe`, choose `Main Cellar` in `[data-testid=sensor-zone]`, and fill `[data-testid=sensor-external]` with a new id. Choose `[data-testid=sensor-create]`. `[data-testid=sensor-secret]` is visible.
- **Import.** Set `[data-testid=sensor-csv]` to a CSV whose header is `sensor,timestamp,metric,value` and whose row is that external id, the current UTC time, `temperature_c`, and `30`. Choose `[data-testid=sensor-preview]`. `[data-testid=sensor-preview-row]` contains `excursion`. Choose `[data-testid=sensor-apply]`.
- **Tonight.** Open `/`. `[data-testid=tonight-storage-alert]` contains `Main Cellar`. `[data-testid=tonight-reminder]` contains `ABC license renewal`.
- **Read back.** `curl -sS http://127.0.0.1:8123/sensors` includes `Cellar probe`.
- **Proof.** Screenshot the preview row and the Tonight alert.

## Gotchas

- The secret is shown once, on the create response. Do not require it after a reload.
- `30` is outside the Main Cellar band (12–14°C). A reading inside the band does not raise the excursion line.
