# RP2040 (Pico W) DHT11 to Prometheus Pushgateway

A MicroPython script for the Raspberry Pi Pico W that reads temperature and humidity data from a DHT11 sensor and pushes the metrics to a Prometheus Pushgateway.

## Overview

`main.py` is a MicroPython application that:
1. Connects to WiFi
2. Periodically reads temperature and humidity from a DHT11 sensor
3. Formats the data in Prometheus text exposition format
4. Pushes the metrics to a Prometheus Pushgateway
5. Handles errors gracefully and provides status feedback via the onboard LED

## Configuration

Edit the following user config variables at the top of `main.py`:

- **WIFI_SSID**: WiFi network name
- **WIFI_PASSWORD**: WiFi password
- **ADJUST_TEMP**: Temperature calibration offset (°C)
- **ADJUST_HUMID**: Humidity calibration offset (%)
- **JOB_NAME**: Prometheus job name for metric identification
- **DHT_PIN**: GPIO pin number where the DHT11 sensor is connected (default: 28)
- **READ_INTERVAL_SEC**: How often to read and push metrics (seconds)
- **PUSHGATEWAY_HOST**: Hostname or IP of the Prometheus Pushgateway
- **PUSHGATEWAY_PORT**: Port of the Pushgateway (default: 9091)

## Key Functions

### `wifi_connect(ssid, password, timeout=20)`
Establishes a WiFi connection with automatic timeout handling. Returns the device's IP configuration.

### `build_payload(temp_c, hum_pc, ok=True, err_msg=None)`
Constructs a Prometheus text exposition format payload containing:
- **pico_up**: Gauge indicating if the device is functioning (0 or 1)
- **room_temp_c**: Temperature reading in Celsius (or NaN on error)
- **room_humidity_percent**: Humidity reading as percentage (or NaN on error)
- **pico_last_error**: Info metric with error message if a read/push fails

### `push_with_requests(url, payload)`
Attempts to push metrics using the `urequests` library via HTTP PUT. Falls back to socket method if unavailable.

### `push_with_socket(host, port, url_path, payload)`
Fallback method using raw sockets to send metrics via HTTP PUT, useful if `urequests` is not available.

### `push_to_pushgateway(payload)`
Routes the payload to the Pushgateway at `/metrics/job/<job>/instance/<instance>`, prioritizing `urequests` if available.

### `main()`
Main loop that:
1. Connects to WiFi (with reconnection attempts)
2. Reads sensor data every `READ_INTERVAL_SEC` seconds
3. Builds and pushes the Prometheus payload
4. Blinks the LED to provide visual status feedback
5. Increases delay to 30+ seconds on push failures to avoid spamming

## Error Handling

- **WiFi failures**: Device attempts reconnection each cycle
- **Sensor read failures**: Reports error metric and blinks LED 10 times
- **Push failures**: Reports error metric, blinks LED 10 times, and increases retry delay to 30 seconds

## LED Behavior

- **20 toggles at 3-second intervals** after each successful/attempted cycle
- **10 rapid toggles (1-second intervals)** on sensor read or push failures

## Dependencies

- `network`: WiFi connectivity
- `machine`: GPIO control
- `dht`: DHT11/DHT22 sensor driver
- `urequests` (optional): HTTP requests library for easier payload pushing
- Built-in MicroPython modules: `time`, `ubinascii`, `usocket`

## Metrics Pushed to Prometheus

The script pushes metrics in the following format to the Pushgateway:

```
pico_up{job="upstairs_dht11",instance="<device_id>"} 1
room_temp_c{sensor="dht11",instance="<device_id>"} 23.5
room_humidity_percent{sensor="dht11",instance="<device_id>"} 45.2
```

On errors:
```
pico_up{job="upstairs_dht11",instance="<device_id>"} 0
pico_last_error{instance="<device_id>",message="DHT read failed: ..."} 1
```

## Usage

1. Configure WiFi and Pushgateway settings
2. Connect the DHT11 sensor to the configured GPIO pin
3. Upload `main.py` to the Pico W
4. The script will automatically start and begin pushing metrics
