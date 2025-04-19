import network
import socket
import time
from machine import Pin
import camera
import gc

# Camera configuration for AI Thinker ESP32-CAM
camera_config = {
    'pin_pwdn': 32,
    'pin_reset': -1,
    'pin_xclk': 0,
    'pin_sccb_sda': 26,
    'pin_sccb_scl': 27,
    'pin_d7': 35,
    'pin_d6': 34,
    'pin_d5': 39,
    'pin_d4': 36,
    'pin_d3': 21,
    'pin_d2': 19,
    'pin_d1': 18,
    'pin_d0': 5,
    'pin_vsync': 25,
    'pin_href': 23,
    'pin_pclk': 22,
    'xclk_freq': 20000000,
    'framesize': camera.FRAME_UXGA,  # UXGA size (1600x1200)
    'pixel_format': camera.PIXFORMAT_JPEG,
    'jpeg_quality': 10,
    'fb_count': 2
}

# WiFi credentials
SSID = "Infinix NOTE 30"
PASSWORD = "10902493"

# LED pin (GPIO4)
led = Pin(4, Pin.OUT)
led.value(1)  # Turn on LED

# Initialize camera
try:
    camera.init(camera_config)
except Exception as e:
    print("Camera init failed:", e)
    led.value(0)  # Turn off LED if camera fails
    raise

# Connect to WiFi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

while not wlan.isconnected():
    led.value(not led.value())  # Toggle LED while connecting
    time.sleep(0.5)

led.value(1)  # LED on when connected
print("WiFi connected:", wlan.ifconfig())

# HTML content for the root page
html = """<html>
<head><title>ESP32-CAM Stream</title></head>
<body>
<h1>ESP32-CAM Stream</h1>
<img src="/stream" width="640" height="480">
</body>
</html>"""

# Boundary for MJPEG stream
BOUNDARY = "123456789000000000000987654321"
STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" + BOUNDARY
STREAM_BOUNDARY = "\r\n--" + BOUNDARY + "\r\n"
STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %s\r\n\r\n"

def handle_client(conn):
    request = conn.recv(1024)
    request = str(request)
    
    # Handle root request
    if "/stream" not in request:
        conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
        conn.send(html)
        conn.close()
        return
    
    # Handle MJPEG stream request
    conn.send("HTTP/1.1 200 OK\r\n")
    conn.send("Content-Type: " + STREAM_CONTENT_TYPE + "\r\n")
    conn.send("Connection: close\r\n")
    conn.send("\r\n")
    
    try:
        while True:
            # Capture frame
            frame = camera.capture()
            if not frame:
                print("Failed to capture frame")
                break
            
            # Send frame
            conn.send(STREAM_BOUNDARY)
            conn.send(STREAM_PART % len(frame))
            conn.send(frame)
            
            # Small delay to prevent high CPU usage
            time.sleep(0.1)
            
            # Clean up
            gc.collect()
            
    except Exception as e:
        print("Stream error:", e)
    finally:
        conn.close()

# Create server socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('0.0.0.0', 80))
server_socket.listen(5)
print("Camera streaming server started on", wlan.ifconfig()[0])

# Main loop to handle clients
try:
    while True:
        conn, addr = server_socket.accept()
        print("Client connected from", addr)
        handle_client(conn)
except Exception as e:
    print("Server error:", e)
    server_socket.close()
    led.value(0)
