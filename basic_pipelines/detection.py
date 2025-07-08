import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
import threading
import time
import datetime
import supervision as sv
import logging


from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from person_counter_web import start_web_interface
from google_logger import GoogleSheetLogger  # hvis du gemmer det i fx `google_logger.py`
from led_controller import LEDController



# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        #self.use_frame = True
        #self.new_variable = 42  # New variable example
        self.unique_ids = set()
        self.total_in = 0
        self.total_out = 0
        self.track_positions = {}  # track_id -> previous y position
        self.logger = GoogleSheetLogger()
        self.log_interval = 60
        self._stop_log_thread = threading.Event()
        self.log_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.log_thread.start()
        self.led = LEDController(pin_in=19, pin_out=26)
        self.led.flash_out()
        self.led.flash_in()
        logging.getLogger("picamera2").setLevel(logging.CRITICAL)
        self.already_counted_in = set()
        self.already_counted_out = set()
        

    def _log_worker(self):
        while not self._stop_log_thread.is_set():
            # Get the current values directly (not from queue)
            total_in = self.total_in
            total_out = self.total_out
            self.logger.log(total_in, total_out)
            # Sleep until next 30-second boundary (optional, for clean logs)
            now = time.time()
            sleep_sec = 60 - (now % 60)
            time.sleep(sleep_sec)
            print("Logger nu:", datetime.datetime.now().strftime("%H:%M:%S"))
    
    def stop_log_thread(self):
        self._stop_log_thread.set()
        self.log_thread.join()

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------

# This is the callback function that will be called when data is available from the pipeline
def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    #string_to_print = f"Frame count: {user_data.get_count()}\n"

    format, width, height = get_caps_from_pad(pad)

    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        frame = get_numpy_from_buffer(buffer, format, width, height)

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    detection_count = 0
    line_y = int(height / 2)

    
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()

        if label == "person":
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) == 1:
                track_id = track[0].get_id()

                # Beregn center af personens bounding box
                x_center = int((bbox.xmin()*width + bbox.xmax()*width) / 2)
                y_center = int((bbox.ymin()*height  + bbox.ymax()*height) / 2)

                prev_y = user_data.track_positions.get(track_id, None)
                user_data.track_positions[track_id] = y_center

                if prev_y is not None:
                    if prev_y < line_y and y_center >= line_y:
                        if track_id not in user_data.already_counted_in:
                            user_data.total_in += 1
                            user_data.led.flash_in()
                            user_data.already_counted_in.add(track_id)
                    elif prev_y > line_y and y_center <= line_y:
                        if track_id not in user_data.already_counted_out:
                            user_data.total_out += 1
                            user_data.led.flash_out()
                            user_data.already_counted_out.add(track_id)
                    
       
            detection_count += 1
            string_to_print = (f"Detection: ID: {track_id} Label: {label} Confidence: {confidence:.2f}\n")
            string_to_print += (
                f"Total IN: {user_data.total_in}\n"
                f"Total OUT: {user_data.total_out}\n")
            print(string_to_print)

            x1 = int(bbox.xmin() * width)
            y1 = int(bbox.ymin() * height)
            x2 = int(bbox.xmax() * width)
            y2 = int(bbox.ymax() * height)


            color = (255, 0, 0)  # BGR

            # Tegn boksen
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"ID: {track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if user_data.use_frame:
        # Tegn linje
        cv2.line(frame, (0, line_y), (width, line_y), (255, 255, 0), 2)
        cv2.putText(frame, "COUNT LINE", (10, line_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        # Tegn taelling
        cv2.putText(frame, f"In: {user_data.total_in}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"Out: {user_data.total_out}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        user_data.set_frame(frame)
        
   
        current_ids = set([track[0].get_id() for detection in detections if detection.get_label() == "person" 
        for track in [detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)] if len(track) == 1])
        user_data.already_counted_in &= current_ids
        user_data.already_counted_out &= current_ids
    #cv2.putText(frame, "COUNT LINE", (10, line_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    
    # I din callback eller loop:

    return Gst.PadProbeReturn.OK


if __name__ == "__main__":
    
    user_data = user_app_callback_class()
    #user_data.use_frame = True  # vigtigt!
    
    try:
        start_web_interface(user_data)
        # Start GStreamer app
        app = GStreamerDetectionApp(app_callback, user_data)
        app.run()
    finally:
        user_data.stop_log_thread()
