#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "esp_camera.h"

// Pin definitions
#define YELLOW_BUTTON 26
#define RED_BUTTON 27
#define GREEN_BUTTON 25
#define RST_PIN 21
#define SS_PIN 5
#define SCK_PIN 18
#define MOSI_PIN 23
#define MISO_PIN 19

// WiFi and MQTT settings
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* mqtt_server = "broker.emqx.io";
const char* mqtt_topic = "/predict/classes";
const char* clientID = "tapngo_payment_system";

// Camera configuration (for ESP32-CAM)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// System objects
LiquidCrystal_I2C lcd(0x27, 20, 4);
MFRC522 mfrc522(SS_PIN, RST_PIN);
WiFiClient espClient;
PubSubClient client(espClient);

// State management
enum SystemState {
  WELCOME,
  SCAN_CARD,
  MAIN_MENU,
  PROCESSING,
  PAYMENT_CONFIRMATION,
  PAYMENT_PROCESSING,
  PAYMENT_SUCCESS,
  PAYMENT_CANCELLED
};

SystemState currentState = WELCOME;
unsigned long lastStateChange = 0;
String detectedFood = "Bento"; // Default value
bool cameraActive = false;

void setup() {
  Serial.begin(115200);
  
  // Initialize LCD
  Wire.begin(33, 32);
  lcd.init();
  lcd.backlight();
  
  // Initialize RFID
  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
  mfrc522.PCD_Init();
  
  // Initialize buttons
  pinMode(YELLOW_BUTTON, INPUT_PULLUP);
  pinMode(RED_BUTTON, INPUT_PULLUP);
  pinMode(GREEN_BUTTON, INPUT_PULLUP);
  
  // Connect to WiFi
  setup_wifi();
  
  // Setup MQTT
  client.setServer(mqtt_server, 1883);
  client.setCallback(mqtt_callback);
  
  // Initialize camera (will be activated when needed)
  setup_camera();
}

void loop() {
  if (!client.connected()) {
    reconnect_mqtt();
  }
  client.loop();

  bool newCardPresent = mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial();
  
  switch(currentState) {
    case WELCOME:
      displayWelcome();
      if (digitalRead(GREEN_BUTTON) == LOW) {
        changeState(SCAN_CARD);
      }
      break;
      
    case SCAN_CARD:
      displayScanCard();
      if (newCardPresent) {
        changeState(MAIN_MENU);
      }
      break;
      
    case MAIN_MENU:
      displayMainMenu();
      if (digitalRead(YELLOW_BUTTON) == LOW) {
        activate_camera();
        changeState(PROCESSING);
      }
      break;
      
    case PROCESSING:
      displayProcessing();
      // Camera is streaming and MQTT will receive food type
      if (detectedFood != "" && millis() - lastStateChange > 2000) {
        deactivate_camera();
        changeState(PAYMENT_CONFIRMATION);
      }
      break;
      
    case PAYMENT_CONFIRMATION:
      displayPaymentConfirmation();
      if (digitalRead(GREEN_BUTTON) == LOW) {
        changeState(PAYMENT_PROCESSING);
      } else if (digitalRead(RED_BUTTON) == LOW) {
        changeState(PAYMENT_CANCELLED);
      }
      break;
      
    case PAYMENT_PROCESSING:
      displayPaymentProcessing();
      if (newCardPresent) {
        changeState(PAYMENT_SUCCESS);
      }
      break;
      
    case PAYMENT_SUCCESS:
      displayPaymentSuccess();
      if (millis() - lastStateChange > 3000) {
        changeState(WELCOME);
      }
      break;
      
    case PAYMENT_CANCELLED:
      displayPaymentCancelled();
      if (millis() - lastStateChange > 3000) {
        changeState(WELCOME);
      }
      break;
  }
  
  if (newCardPresent) {
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
  }
  
  delay(100);
}

void setup_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  if(psramFound()){
    config.frame_size = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }
  
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }
}

void activate_camera() {
  cameraActive = true;
  // Start streaming (implementation depends on your streaming method)
  Serial.println("Camera streaming started");
  client.subscribe(mqtt_topic);
}

void deactivate_camera() {
  cameraActive = false;
  client.unsubscribe(mqtt_topic);
  Serial.println("Camera streaming stopped");
}

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect_mqtt() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(clientID)) {
      Serial.println("connected");
      client.subscribe(mqtt_topic);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void mqtt_callback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  // Process food detection results
  if (message == "bento" || message == "rice-bowl") {
    detectedFood = message;
    detectedFood.toUpperCase();
    Serial.println("Detected food: " + detectedFood);
  }
}

void changeState(SystemState newState) {
  currentState = newState;
  lastStateChange = millis();
  lcd.clear();
}

void displayWelcome() {
  lcd.setCursor(2, 0);
  lcd.print("SELAMAT DATANG DI");
  lcd.setCursor(4, 1);
  lcd.print("TAP N GO");
  lcd.setCursor(2, 3);
  lcd.print("Klik OK");
}

void displayScanCard() {
  lcd.setCursor(2, 1);
  lcd.print("SILAHKAN TEMPEL");
  lcd.setCursor(4, 2);
  lcd.print("KARTU ANDA");
}

void displayMainMenu() {
  lcd.setCursor(2, 0);
  lcd.print("SILAHKAN TARUH");
  lcd.setCursor(1, 1);
  lcd.print("MAKANAN/MINUMAN");
  lcd.setCursor(5, 2);
  lcd.print("ANDA LALU");
  lcd.setCursor(6, 3);
  lcd.print("TEKAN CONFIRM");
}

void displayProcessing() {
  lcd.setCursor(6, 1);
  lcd.print("SEDANG");
  lcd.setCursor(4, 2);
  lcd.print("MENGENALI MAKANAN");
}

void displayPaymentConfirmation() {
  lcd.setCursor(0, 0);
  lcd.print("ITEM: " + detectedFood);
  lcd.setCursor(0, 1);
  lcd.print("QTY: 1x");
  
  // Calculate price based on food type
  int price = (detectedFood == "BENTO") ? 10000 : 15000;
  lcd.setCursor(0, 2);
  lcd.print("Harga Total: Rp" + String(price));
  
  lcd.setCursor(5, 3);
  lcd.print("[OK]   [Cancel]");
}

void displayPaymentProcessing() {
  lcd.setCursor(3, 1);
  lcd.print("TEMPELKAN KARTU");
  lcd.setCursor(4, 2);
  lcd.print("UNTUK PEMBAYARAN");
}

void displayPaymentSuccess() {
  lcd.setCursor(4, 1);
  lcd.print("PEMBAYARAN");
  lcd.setCursor(5, 2);
  lcd.print("SUKSES!");
  lcd.setCursor(2, 3);
  lcd.print("TERIMA KASIH");
}

void displayPaymentCancelled() {
  lcd.setCursor(3, 1);
  lcd.print("PEMBELIAN");
  lcd.setCursor(4, 2);
  lcd.print("DIBATALKAN");
  lcd.setCursor(2, 3);
  lcd.print("TERIMA KASIH");
}
