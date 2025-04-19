from ultralytics import YOLO
import cv2
import paho.mqtt.client as mqtt
import time
import os
from dotenv import load_dotenv

load_dotenv()

# MQTT setup
mqttc = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=os.getenv("CLIENT_ID")
)
mqttc.connect(os.getenv("MQTT_SERVER"), int(os.getenv("MQTT_PORT")))
mqttc.loop_start()

# YOLOv8 Model
model = YOLO('tap-n-go-detection.pt')

# ESP32-CAM Setup
cam = cv2.VideoCapture(os.getenv("ESP32_CAM_URL"))

if not cam.isOpened():
    print("Failed to connect to ESP32-CAM stream")
    exit()

# Throttling Variables
last_publish_time = 0
PUBLISH_INTERVAL = 3  # Seconds

while True:
    ret, frame = cam.read()
    if not ret:
        print("Frame retrieval error, trying to reconnect...")
        cam.release()
        time.sleep(2)
        cam = cv2.VideoCapture(os.getenv("ESP32_CAM_URL"))
        continue

    # YOLOv8 Inference
    results = model.predict(frame, conf=0.6)
    detected_classes = set()

    # Process Results
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls.item())
            detected_classes.add(model.names[cls_id])

    # Throttled MQTT Publishing
    current_time = time.time()
    if current_time - last_publish_time >= PUBLISH_INTERVAL:
        msg = ",".join(detected_classes) if detected_classes else "NONE"
        mqttc.publish(os.getenv("MQTT_TOPIC"), msg)
        last_publish_time = current_time

    # Display Annotated Frame
    cv2.imshow('ESP32-CAM Feed', results[0].plot())
    if cv2.waitKey(1) == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()
