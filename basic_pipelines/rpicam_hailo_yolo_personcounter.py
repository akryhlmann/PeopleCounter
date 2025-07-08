# rpicam_gst_yolo_pipeline.py

import gi
import os
import cv2
import hailo
from gi.repository import Gst, GLib

from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

Gst.init(None)

# Brugertilpasset callback klasse
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.total_in = 0
        self.total_out = 0
        self.track_positions = {}
        self.use_frame = True

# Callback funktion med taellelogik
def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()

    format, width, height = get_caps_from_pad(pad)

    frame = None
    if user_data.use_frame and format and width and height:
        frame = get_numpy_from_buffer(buffer, format, width, height)

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    line_y = int(height / 2)

    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()

        if label == "person" and confidence > 0.5:
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) == 1:
                track_id = track[0].get_id()

            cx = int((bbox.xmin() + bbox.xmax()) / 2)
            cy = int((bbox.ymin() + bbox.ymax()) / 2)

            prev_y = user_data.track_positions.get(track_id)
            user_data.track_positions[track_id] = cy

            if prev_y is not None:
                if prev_y < line_y and cy >= line_y:
                    user_data.total_in += 1
                elif prev_y > line_y and cy <= line_y:
                    user_data.total_out += 1

    if user_data.use_frame:
        cv2.line(frame, (0, line_y), (width, line_y), (255, 255, 0), 2)
        cv2.putText(frame, f"IN: {user_data.total_in}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"OUT: {user_data.total_out}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        user_data.set_frame(frame)

    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    user_data = user_app_callback_class()

    # Dynamisk opbygning af GStreamer pipeline med rpicam, Hailo og YOLO post-process
    os.environ["GST_DEBUG_DUMP_DOT_DIR"] = "/tmp"  # Debug-valgfrit

    pipeline_str = (
        "libcamerasrc ! video/x-raw,width=640,height=480,framerate=30/1 ! "
        "videoconvert ! hailonet hef-path=/path/til/yolo_model.hef ! "
        "yolopostprocess config-path=/path/til/yolo_postprocess_config.json ! appsink name=appsink"
    )

    print("Starter pipeline:", pipeline_str)

    app = GStreamerDetectionApp(app_callback, user_data, pipeline_override=pipeline_str)
    user_data.use_frame = True

    app.run()
