from machine import Pin, SPI, I2C
import time
import network
from umqtt.simple import MQTTClient
import ubinascii
import mfrc522
from esp32_cam import Camera  # You'll need to implement this separately
from lcd_i2c import LCD  # You'll need an I2C LCD library for MicroPython

# Pin definitions
YELLOW_BUTTON = Pin(26, Pin.IN, Pin.PULL_UP)
RED_BUTTON = Pin(27, Pin.IN, Pin.PULL_UP)
GREEN_BUTTON = Pin(25, Pin.IN, Pin.PULL_UP)
RST_PIN = Pin(21, Pin.OUT)
SS_PIN = Pin(5, Pin.OUT)

# SPI for RFID
spi = SPI(1, baudrate=2500000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
rfid = mfrc522.MFRC522(spi, RST_PIN, SS_PIN)

# I2C for LCD
i2c = I2C(0, scl=Pin(32), sda=Pin(33))
lcd = LCD(i2c, 0x27, 20, 4)  # Adjust based on your LCD library

# WiFi and MQTT settings
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
MQTT_BROKER = "broker.emqx.io"
MQTT_TOPIC = b"/predict/classes"
CLIENT_ID = ubinascii.hexlify(machine.unique_id())

# System state
class SystemState:
    WELCOME = 0
    SCAN_CARD = 1
    MAIN_MENU = 2
    PROCESSING = 3
    PAYMENT_CONFIRMATION = 4
    PAYMENT_PROCESSING = 5
    PAYMENT_SUCCESS = 6
    PAYMENT_CANCELLED = 7

current_state = SystemState.WELCOME
last_state_change = time.ticks_ms()
detected_food = "Bento"  # Default value
camera_active = False

# Initialize camera (you'll need to implement this)
camera = Camera()

# WiFi connection
def connect_wifi():
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to WiFi...')
        sta_if.active(True)
        sta_if.connect(WIFI_SSID, WIFI_PASS)
        while not sta_if.isconnected():
            pass
    print('Network config:', sta_if.ifconfig())

# MQTT callback
def mqtt_callback(topic, msg):
    global detected_food
    message = msg.decode()
    
    if message in ["bento", "rice-bowl"]:
        detected_food = message.upper()
        print("Detected food:", detected_food)

# Connect to MQTT
def connect_mqtt():
    client = MQTTClient(CLIENT_ID, MQTT_BROKER)
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(MQTT_TOPIC)
    print("Connected to MQTT broker")
    return client

try:
    mqtt_client = connect_mqtt()
except Exception as e:
    print("MQTT connection failed:", e)

# State display functions
def display_welcome():
    lcd.clear()
    lcd.putstr("SELAMAT DATANG DI")
    lcd.set_cursor(0, 1)
    lcd.putstr("    TAP N GO    ")
    lcd.set_cursor(0, 3)
    lcd.putstr("    Klik OK     ")

def display_scan_card():
    lcd.clear()
    lcd.set_cursor(0, 1)
    lcd.putstr(" SILAHKAN TEMPEL ")
    lcd.set_cursor(0, 2)
    lcd.putstr("   KARTU ANDA   ")

def display_main_menu():
    lcd.clear()
    lcd.set_cursor(0, 0)
    lcd.putstr(" SILAHKAN TARUH ")
    lcd.set_cursor(0, 1)
    lcd.putstr("MAKANAN/MINUMAN")
    lcd.set_cursor(0, 2)
    lcd.putstr("  ANDA LALU   ")
    lcd.set_cursor(0, 3)
    lcd.putstr(" TEKAN CONFIRM ")

def display_processing():
    lcd.clear()
    lcd.set_cursor(0, 1)
    lcd.putstr("     SEDANG     ")
    lcd.set_cursor(0, 2)
    lcd.putstr(" MEMPROSES...  ")

def display_payment_confirmation():
    lcd.clear()
    lcd.set_cursor(0, 0)
    lcd.putstr("ITEM: " + detected_food)
    lcd.set_cursor(0, 1)
    lcd.putstr("QTY: 1x")
    
    # Calculate price based on food type
    price = 10000 if detected_food == "BENTO" else 15000
    lcd.set_cursor(0, 2)
    lcd.putstr("Harga: Rp{}".format(price))
    
    lcd.set_cursor(0, 3)
    lcd.putstr(" [OK]   [Cancel] ")

def display_payment_processing():
    lcd.clear()
    lcd.set_cursor(0, 1)
    lcd.putstr(" TEMPELKAN KARTU ")
    lcd.set_cursor(0, 2)
    lcd.putstr("UNTUK PEMBAYARAN")

def display_payment_success():
    lcd.clear()
    lcd.set_cursor(0, 1)
    lcd.putstr("  PEMBAYARAN   ")
    lcd.set_cursor(0, 2)
    lcd.putstr("    SUKSES!    ")
    lcd.set_cursor(0, 3)
    lcd.putstr("  TERIMA KASIH ")

def display_payment_cancelled():
    lcd.clear()
    lcd.set_cursor(0, 1)
    lcd.putstr("  PEMBELIAN   ")
    lcd.set_cursor(0, 2)
    lcd.putstr(" DIBATALKAN  ")
    lcd.set_cursor(0, 3)
    lcd.putstr(" TERIMA KASIH ")

def change_state(new_state):
    global current_state, last_state_change
    current_state = new_state
    last_state_change = time.ticks_ms()
    lcd.clear()

# Main loop
while True:
    # Check for RFID card
    (status, tag_type) = rfid.request(rfid.REQIDL)
    card_present = status == rfid.OK
    
    # Handle MQTT messages
    try:
        mqtt_client.check_msg()
    except:
        # Try to reconnect if connection lost
        try:
            mqtt_client = connect_mqtt()
        except:
            pass
    
    # State machine
    if current_state == SystemState.WELCOME:
        display_welcome()
        if GREEN_BUTTON.value() == 0:
            change_state(SystemState.SCAN_CARD)
    
    elif current_state == SystemState.SCAN_CARD:
        display_scan_card()
        if card_present:
            change_state(SystemState.MAIN_MENU)
    
    elif current_state == SystemState.MAIN_MENU:
        display_main_menu()
        if YELLOW_BUTTON.value() == 0:
            # Activate camera
            camera_active = True
            camera.start_streaming()
            change_state(SystemState.PROCESSING)
    
    elif current_state == SystemState.PROCESSING:
        display_processing()
        if detected_food != "Bento" and time.ticks_diff(time.ticks_ms(), last_state_change) > 2000:
            # Deactivate camera after detection
            camera_active = False
            camera.stop_streaming()
            change_state(SystemState.PAYMENT_CONFIRMATION)
    
    elif current_state == SystemState.PAYMENT_CONFIRMATION:
        display_payment_confirmation()
        if GREEN_BUTTON.value() == 0:
            change_state(SystemState.PAYMENT_PROCESSING)
        elif RED_BUTTON.value() == 0:
            change_state(SystemState.PAYMENT_CANCELLED)
    
    elif current_state == SystemState.PAYMENT_PROCESSING:
        display_payment_processing()
        if card_present:
            change_state(SystemState.PAYMENT_SUCCESS)
    
    elif current_state == SystemState.PAYMENT_SUCCESS:
        display_payment_success()
        if time.ticks_diff(time.ticks_ms(), last_state_change) > 3000:
            change_state(SystemState.WELCOME)
    
    elif current_state == SystemState.PAYMENT_CANCELLED:
        display_payment_cancelled()
        if time.ticks_diff(time.ticks_ms(), last_state_change) > 3000:
            change_state(SystemState.WELCOME)
    
    time.sleep_ms(100)
