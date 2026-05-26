# MicroPython: RP2040 (Pico W) + DHT11 -> Prometheus Pushgateway
# Pushes to http://www.gardner.link:9093/metrics/job/<job>/instance/<instance>

import time
import machine
from machine import Pin
import network
import dht
import ubinascii
import usocket

# ---- User config ----
WIFI_SSID = "pepernoot"
WIFI_PASSWORD = "tabletop"

# ---- Adjust per dht11 ----
ADJUST_TEMP=-3
ADJUST_HUMID=2
JOB_NAME = "upstairs_dht11"

# ---- Adjust for Gateway ----
DHT_PIN = 28                     # GP15 by default; change if needed
READ_INTERVAL_SEC = 15           # how often to read & push
PUSHGATEWAY_HOST = "pushgateway.lan"
PUSHGATEWAY_PORT = 9091
INSTANCE = ubinascii.hexlify(machine.unique_id()).decode()  # unique per board
LED = Pin("LED", Pin.OUT)
# ---------------------

# Optional: try to import urequests; if missing we’ll use socket fallback
try:
    import urequests as requests
except Exception:
    requests = None

def wifi_connect(ssid, password, timeout=20):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        t0 = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout * 1000:
                raise RuntimeError("Wi-Fi connection timed out")
            time.sleep(0.25)
    return wlan.ifconfig()

def build_payload(temp_c, hum_pc, ok=True, err_msg=None):
    """
    Prometheus text exposition format.
    Use a single 'up' metric to indicate scrape success, plus the readings.
    """
    lines = []
    lines.append("# TYPE pico_up gauge")
    lines.append(f"pico_up{{job=\"{JOB_NAME}\",instance=\"{INSTANCE}\"}} {1 if ok else 0}")

    lines.append("# TYPE room_temp_c gauge")
    lines.append(f"room_temp_c{{sensor=\"dht11\",instance=\"{INSTANCE}\"}} {temp_c if ok else 'NaN'}")

    lines.append("# TYPE room_humidity_percent gauge")
    lines.append(f"room_humidity_percent{{sensor=\"dht11\",instance=\"{INSTANCE}\"}} {hum_pc if ok else 'NaN'}")

    if not ok and err_msg:
        # Attach the last error as an info metric (label value must be quoted)
        esc = err_msg.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        lines.append("# TYPE pico_last_error info")
        lines.append(f"pico_last_error{{instance=\"{INSTANCE}\",message=\"{esc}\"}} 1")

    return "\n".join(lines) + "\n"

def push_with_requests(url, payload):
    try:
        r = requests.put(url, data=payload, headers={"Content-Type": "text/plain"})
        try:
            code = r.status_code
        finally:
            r.close()
        if code // 100 != 2:
            raise RuntimeError("Pushgateway returned HTTP %d" % code)
        return True
    except Exception as e:
        print("requests push failed:", e)
        return False

def push_with_socket(host, port, url_path, payload):
    # Minimal HTTP/1.1 PUT via sockets
    addr_info = usocket.getaddrinfo(host, port, 0, usocket.SOCK_STREAM)[0][-1]
    s = usocket.socket()
    try:
        s.connect(addr_info)
        req = (
            "PUT {} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "User-Agent: pico-w-mpy\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
            "{}"
        ).format(url_path, host, len(payload), payload)
        s.send(req)
        # Read a tiny response head to verify 2xx
        resp = s.recv(128)
        if not resp or b" 2" not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError("Non-2xx response or no response")
        return True
    except Exception as e:
        print("socket push failed:", e)
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass

def push_to_pushgateway(payload):
    # Pushgateway path: /metrics/job/<job>/instance/<instance>
    path = "/metrics/job/{}/instance/{}".format(JOB_NAME, INSTANCE)
    url = "http://{}:{}{}".format(PUSHGATEWAY_HOST, PUSHGATEWAY_PORT, path)
    if requests:
        ok = push_with_requests(url, payload)
        if ok:
            return True
    # Fallback to socket
    return push_with_socket(PUSHGATEWAY_HOST, PUSHGATEWAY_PORT, path, payload)

def main():
    print("Connecting Wi-Fi...")
    try:
        ip, subnet, gateway, dns = wifi_connect(WIFI_SSID, WIFI_PASSWORD)
        print("Wi-Fi up. IP:", ip)
    except Exception as e:
        # Even if Wi-Fi fails initially, we still proceed to retry in loop
        print("Wi-Fi connect failed:", e)

    pin = Pin(DHT_PIN, Pin.IN, Pin.PULL_UP)
    sensor = dht.DHT22(pin)
    led = Pin("LED", Pin.OUT)
    
    while True:
        temp = None
        hum = None
        ok = True
        err = None

        # Ensure Wi-Fi connected (reconnect if needed)
        try:
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                print("Reconnecting Wi-Fi...")
                wifi_connect(WIFI_SSID, WIFI_PASSWORD)
        except Exception as e:
            print("Wi-Fi check/reconnect failed:", e)

        # Read sensor
        try:
            sensor.measure()
            temp = sensor.temperature()    # °C
            hum = sensor.humidity()        # %
            print("T={}°C H={}%" .format(temp, hum))
        except Exception as e:
            ok = False
            err = "DHT read failed: {}".format(e)
            print(err)
            for _ in range(10):
                led.toggle()
                time.sleep(1)

        # For testing push failures
        #
        # hum = 59
        # temp = 23
        # ok = True
            
        # Build & push
        try:
            payload = build_payload(temp, hum, ok=ok, err_msg=err)
            pushed = push_to_pushgateway(payload)
            print("Pushed:", pushed)
        except Exception as e:
            ok = False
            err = "DHT push failed: {}".format(e)
            print(err)
            for _ in range(10):
                led.toggle()
                time.sleep(1)
        
        # Basic backoff on failure to avoid spamming
        delay = READ_INTERVAL_SEC if pushed else max(READ_INTERVAL_SEC, 30)
        
        # Blink the LED twenty times at 3-second intervals
        for _ in range(20):
            led.toggle()
            time.sleep(3)
        
        # Optional: wait out the remainder of the delay (if you still need the original pacing)
        remaining = delay - 20 * 3
        if remaining > 0:
            time.sleep(remaining)
        
# Run
if __name__ == "__main__":
    main()
