import streamlit as st
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO
import tempfile
import paho.mqtt.client as mqtt
import os
from dotenv import load_dotenv
import time
from streamlit_webrtc import webrtc_streamer
import av

# Load environment variables
load_dotenv()

# Initialize MQTT client
if 'mqttc' not in st.session_state:
    try:
        st.session_state.mqttc = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=os.getenv("CLIENT_ID")
        )
        st.session_state.mqttc.connect(
            os.getenv("MQTT_SERVER"),
            int(os.getenv("MQTT_PORT"))
        )
        st.session_state.mqttc.loop_start()
    except Exception as e:
        st.error(f"MQTT Connection Error: {str(e)}")

model = YOLO('Ahamra1120/Assignment-Escape/streamlit/best.pt')

st.title("🍾 Revoira Object Detection")

# ===== MQTT Status Section =====
with st.sidebar.expander("🔌 MQTT Connection Status", expanded=True):
    try:
        status = "✅ Connected" if st.session_state.mqttc.is_connected() else "❌ Disconnected"
        st.metric(label="MQTT Status", value=status)
        st.caption(f"Broker: {os.getenv('MQTT_SERVER')}:{os.getenv('MQTT_PORT')}")
        st.caption(f"Topic: {os.getenv('MQTT_TOPIC')}")
        st.caption(f"Client ID: {os.getenv('CLIENT_ID')}")
    except Exception as e:
        st.error(f"MQTT Status Error: {str(e)}")

# ===== Model Information Section =====
with st.expander("⚠️ Important Model Notes", expanded=True):
    st.markdown("""
    **Model Specifications:**
                
    This model's purpose was to detect a type of bottles based on its material 
                
    - **List of classes:** 
      - 🥫 can-bottle | 🧴 plastic-bottle | 🍾 glass-bottle | 📦 tetrapak
                
    **Current Limitations:**
                
    Keep in mind that the models will be used in an environment where only such conditions will exists so there will
    be some limitations such as:
                
    1. **Single-Class Detection Preference**  
       The model tends to detect only the most prominent object in a frame when multiple objects are present.  
    
    2. **Optimal Detection Conditions**  
       Works best with:
       - Single objects centered in frame
       - Flat, uniform backgrounds (like conveyor belts)
       - Good lighting conditions
       - Objects placed on solid surfaces
    
    3. **Performance Notes**  
       Detection quality could decreases when:
       - Objects overlap or are too close
       - Backgrounds are cluttered
       - Lighting is uneven or creates shadows
    """)

# Input type selection
input_type = st.sidebar.radio(
    "Select Input Source:",
    ("Image Upload", "Video Upload", "Webcam")
)

# Throttling configuration
PUBLISH_INTERVAL = 3  # Seconds

# ... (previous imports and setup remain the same)

# Throttling configuration
PUBLISH_INTERVAL = 3  # Seconds

class VideoProcessor:
    def __init__(self):
        self.last_publish = 0
        
    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        results = model.predict(img, conf=0.6)
        
        # MQTT Publishing with throttling
        current_time = time.time()
        if current_time - self.last_publish >= PUBLISH_INTERVAL:
            detected_classes = set()
            for result in results:
                for box in result.boxes:
                    cls_id = int(box.cls.item())
                    detected_classes.add(model.names[cls_id])
            
            self.publish_detection(detected_classes)
            self.last_publish = current_time
        
        return av.VideoFrame.from_ndarray(results[0].plot(), format="bgr24")

    def publish_detection(self, detected_classes):
        msg = ",".join(detected_classes) if detected_classes else "NONE"
        try:
            st.session_state.mqttc.publish(os.getenv("MQTT_TOPIC"), msg)
            st.sidebar.success(f"Published: {msg}")
        except Exception as e:
            st.sidebar.error(f"MQTT Error: {str(e)}")

# ===== Image Upload =====
if input_type == "Image Upload":
    img_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])
    
    if img_file is not None:
        image = Image.open(img_file)
        image_np = np.array(image)
        results = model.predict(image_np)
        st.image(results[0].plot(), caption="Processed Image", use_column_width=True)

        # Publish detected classes for image
        detected_classes = set()
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls.item())
                detected_classes.add(model.names[cls_id])
        
        VideoProcessor().publish_detection(detected_classes)

# ===== Video Upload =====
elif input_type == "Video Upload":
    video_file = st.file_uploader("Upload Video", type=["mp4", "avi", "mov"])
    
    if video_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(video_file.read())
        
        cap = cv2.VideoCapture(tfile.name)
        stframe = st.empty()
        last_publish = 0  # Track last publish time

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            results = model.predict(frame)
            stframe.image(results[0].plot(), channels="BGR")

            # Throttled MQTT publishing
            current_time = time.time()
            if current_time - last_publish >= PUBLISH_INTERVAL:
                detected_classes = set()
                for result in results:
                    for box in result.boxes:
                        cls_id = int(box.cls.item())
                        detected_classes.add(model.names[cls_id])
                
                VideoProcessor().publish_detection(detected_classes)
                last_publish = current_time
        
        cap.release()

# ===== Webcam =====
elif input_type == "Webcam":
    st.warning("⚠️ Allow browser camera access when prompted")
    
    webrtc_streamer(
        key="object-detection",
        video_processor_factory=VideoProcessor,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        media_stream_constraints={"video": True, "audio": False}
    )

# Cleanup when app stops
def on_app_close():
    if 'mqttc' in st.session_state:
        st.session_state.mqttc.loop_stop()
        st.session_state.mqttc.disconnect()

import atexit
atexit.register(on_app_close)