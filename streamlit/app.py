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

model = YOLO('best.pt')

# Page configuration
st.set_page_config(
    page_title="Tap N Go Object Detection",
    page_icon="🍔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal CSS that works with dark mode
st.markdown("""
    <style>
        .stFileUploader > div > div {
            border: 2px dashed;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .streamlit-expanderHeader {
            font-size: 1.1em;
            font-weight: bold;
        }
    </style>
""", unsafe_allow_html=True)

# Main title with icon and description
st.title("🍔 Tap N Go Object Detection")
st.markdown("""
    Real-time object detection system for food container classification. 
    Upload images/videos or use live webcam feed.
""")

# ===== Sidebar Sections =====
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Input type selection
    input_type = st.radio(
        "Select Input Source:",
        ("Image Upload", "Video Upload", "Webcam"),
        index=0
    )
    
    # Confidence threshold slider
    confidence_threshold = st.slider(
        "Detection Confidence Threshold",
        min_value=0.1,
        max_value=0.9,
        value=0.6,
        step=0.05,
        help="Adjust the minimum confidence level for detections"
    )
    
    # MQTT Status Section
    with st.expander("🔌 MQTT Connection Status", expanded=True):
        try:
            if st.session_state.mqttc.is_connected():
                st.success("✅ Connected")
            else:
                st.error("❌ Disconnected")
            
            st.caption(f"Broker: {os.getenv('MQTT_SERVER')}:{os.getenv('MQTT_PORT')}")
            st.caption(f"Topic: {os.getenv('MQTT_TOPIC')}")
            st.caption(f"Client ID: {os.getenv('CLIENT_ID')}")
        except Exception as e:
            st.error(f"MQTT Status Error: {str(e)}")

# ===== Model Information Section =====
with st.expander("📌 Model Information & Guidelines", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
            ### 🎯 Model Specifications
            **Purpose:** Detect food containers based on their type
            
            **Classes:**
            - 🍱 bento
            - 🥡 rice-bowl
            
            **Performance Characteristics:**
            - Inference speed: ~40ms per frame (CPU)
            - Input resolution: 640x640
        """)
    
    with col2:
        st.markdown("""
            ### ⚠️ Usage Guidelines
            **Optimal Conditions:**
            - Single centered objects
            - Flat, uniform backgrounds
            - Good lighting conditions
            
            **Limitations:**
            - May miss overlapping objects
            - Performance decreases with:
              - Cluttered backgrounds
              - Poor lighting
              - Similar-looking objects
        """)

# Throttling configuration
PUBLISH_INTERVAL = 3  # Seconds

class VideoProcessor:
    def __init__(self):
        self.last_publish = 0
        
    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        results = model.predict(img, conf=confidence_threshold)
        
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
        
        # Convert results to video frame
        annotated_frame = results[0].plot()
        return av.VideoFrame.from_ndarray(annotated_frame, format="bgr24")

    def publish_detection(self, detected_classes):
        msg = ",".join(detected_classes) if detected_classes else "NONE"
        try:
            st.session_state.mqttc.publish(os.getenv("MQTT_TOPIC"), msg)
            st.sidebar.success(f"Published: {msg}")
        except Exception as e:
            st.sidebar.error(f"MQTT Error: {str(e)}")

# ===== Main Content Area =====
if input_type == "Image Upload":
    st.subheader("📷 Image Detection")
    img_file = st.file_uploader(
        "Upload an image for detection", 
        type=["jpg", "jpeg", "png"],
        help="Upload an image containing food containers"
    )
    
    if img_file is not None:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Original Image**")
            image = Image.open(img_file)
            st.image(image, use_column_width=True)
        
        with col2:
            st.markdown("**Detection Results**")
            image_np = np.array(image)
            results = model.predict(image_np, conf=confidence_threshold)
            st.image(results[0].plot(), use_column_width=True)

        # Publish detected classes for image
        detected_classes = set()
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls.item())
                detected_classes.add(model.names[cls_id])
        
        if detected_classes:
            st.success(f"✅ Detected: {', '.join(detected_classes)}")
        else:
            st.warning("⚠️ No objects detected")
        
        VideoProcessor().publish_detection(detected_classes)

elif input_type == "Video Upload":
    st.subheader("🎥 Video Detection")
    video_file = st.file_uploader(
        "Upload a video for detection", 
        type=["mp4", "avi", "mov"],
        help="Upload a video containing food containers"
    )
    
    if video_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(video_file.read())
        
        cap = cv2.VideoCapture(tfile.name)
        stframe = st.empty()
        last_publish = 0  # Track last publish time

        # Add a stop button
        stop_button = st.button("Stop Processing")
        
        while cap.isOpened() and not stop_button:
            ret, frame = cap.read()
            if not ret:
                break
            
            results = model.predict(frame, conf=confidence_threshold)
            annotated_frame = results[0].plot()
            stframe.image(annotated_frame, channels="BGR", use_column_width=True)

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
        if stop_button:
            st.warning("Video processing stopped by user")

elif input_type == "Webcam":
    st.subheader("📸 Live Webcam Detection")
    st.info("""
        Allow browser camera access when prompted. 
        Detections will be processed in real-time.
    """)
    
    webrtc_streamer(
        key="object-detection",
        video_processor_factory=VideoProcessor,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True
    )

# Footer
st.markdown("---")
st.markdown("""
**Tap N Go Object Detection System • Powered by YOLOv8**
""")
