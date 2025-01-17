from webcam import Webcam

import numpy as np
import cv2
import time

# import the necessary packages
import datetime

class FPS:
    def __init__(self):
        self._start  = None
        self._end    = None
        self._frames = 0

    def start(self):
        self._start = datetime.datetime.now()
        return self

    def stop(self):
        self._end = datetime.datetime.now()

    def update(self):
        self._frames += 1

    def remove(self, last=1):
        self._frames -= last

    def elapsed(self):
        return (self._end - self._start).total_seconds()

    def fps(self):
        return self._frames / self.elapsed()

    def frames(self):
        self.update()
        self.stop()
        return self.fps()


class HandlerData:
    def __init__(self):
        super().__init__()
        self.info = []
        self.screens = {}

    def add_info(self, data):
        self.info.append(data)

    def add_screen(self, name, frame):
        self.screens[name] = frame


class StaticTracker:
    def __init__(self):
        super().__init__()
        self.box = None

    def init(self, image, boundingBox):
        self.box = boundingBox

    def update(self, image):
        return True, self.box

    @classmethod
    def create(cls, *args):
        return cls()


class ScreenTracker:
    OPENCV_OBJECT_TRACKERS = {
        "csrt"      : cv2.TrackerCSRT_create,
        "kcf"       : cv2.TrackerKCF_create,
        "boosting"  : cv2.TrackerBoosting_create,
        "mil"       : cv2.TrackerMIL_create,
        "tld"       : cv2.TrackerTLD_create,
        "medianflow": cv2.TrackerMedianFlow_create,
        "mosse"     : cv2.TrackerMOSSE_create,
        "static"    : StaticTracker.create
    }

    def __init__(self, input_callback=None, reset_callback=None, tracker="kcf", fps_limit=16, select_key='s', exit_key='q', reset_key='r'):
        super().__init__()

        self.cam          = Webcam(exit_key=exit_key)
        self.tracker      = None
        self.tracker_name = tracker or "static"

        self.width, self.height = 0, 0
        self.box       = None
        self.fps       = FPS()
        self.fps_limit = fps_limit
        self.cropped   = None

        self.tracker_init   = False
        self.dropped_frames = 0

        self._select_key    = select_key
        self._reset_key     = reset_key
        self.input_callback = input_callback
        self.reset_callback = reset_callback

    def start(self):
        try:
            self.cam.capture_start()
            self.width, self.height = self.cam.width, self.cam.height
            self.cam.fps = self.fps_limit
            self.cam.fps = self.fps_limit
            self.cam.fps = self.fps_limit

            while(True):
                # Capture frame-by-frame
                frame = self.cam.capture_new()

                if frame is not None:
                    self._handle_frame(frame)
                    self._use_cropped()
                else:
                    break

                key = cv2.waitKey(1) & 0xFF

                if key == ord(self.cam._exit_key):
                    break
                elif key == ord(self._select_key):
                    self.tracker_init = False
                    self._define_region(frame)
                elif key == ord(self._reset_key) and self.reset_callback:
                    self.reset_callback()

        except KeyboardInterrupt:
            del self.cam

    def _init_tracker(self):
        self.tracker = ScreenTracker.OPENCV_OBJECT_TRACKERS[self.tracker_name]()

    def _define_region(self, frame, title="Select the screen"):
        # Select Region of Interest and start tracker
        initBB = cv2.selectROI(title, frame, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow(title)

        if self.reset_callback:
            self.reset_callback()

        if any(initBB):
            self._init_tracker()
            self.tracker.init(frame, initBB)

            self.fps = FPS().start()
            self.tracker_init = True
            time.sleep(0.1)

    def _handle_frame(self, frame):
        if self.tracker_init:
            # Get and draw track box
            success, self.box = self.tracker.update(frame)
            if success:
                x, y, w, h = (int(v) for v in self.box)
                self.cropped = frame[y:y+h, x:x+w].copy()
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Update fps
            frames = self.fps.frames()

            # Drop frame on fps limit
            if frames > self.fps_limit:
                self.fps.remove()
                self.cropped = None
                self.dropped_frames += 1

            # Draw info
            info = [
                ("Success", "Yes" if success else "No"),
                ("FPS", "{:.2f}".format(frames)),
                ("Dropped", f"{self.dropped_frames} frames"),
            ]

            for i, (k, v) in enumerate(info):
                cv2.putText(frame, "{0}: {1}".format(k, v), (10, (i * 20) + 20),
                            cv2.FONT_HERSHEY_COMPLEX, 0.5, (0, 0, 255), 1)

        cv2.putText(frame, f"(Hit {self._select_key} for select, {self._reset_key} for reset, {self.cam._exit_key} for exit)",
                    (10, self.height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

        # Display the image
        cv2.imshow("Track screen", frame)

    def _use_cropped(self):
        # self.cropped is a np array
        top, bottom, left, right = 0, 0, 0, 0
        target_w, target_h = 500, 500
        line_height, lines = 15, 10
        offset = target_h - ((lines + 1) * line_height)

        if self.cropped is not None and self.cropped.size > 0:
            if self.input_callback:
                # Look at brightness etc
                data = self.input_callback(self.cropped)

                if isinstance(data, HandlerData):
                    if data.screens:
                        all_frames = np.hstack(tuple(data.screens.values()))

                        right, bottom = max(0, target_w - all_frames.shape[1]), \
                                        max(0, target_h - all_frames.shape[0])

                        larger = cv2.copyMakeBorder(all_frames, top, bottom, left, right, cv2.BORDER_CONSTANT, None, (0, 0, 0))

                    total_width = 0
                    for i, (name, frame) in enumerate(data.screens.items(), start=1):
                        h, w    = frame.shape[0], frame.shape[1]
                        (fw, fh), base = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        if not fw: fw = len(name) * 15

                        tw = (w // 2) - (fw // 2)

                        cv2.putText(larger, name,
                                    (total_width + tw, h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        total_width += w

                    for i, line in enumerate(data.info, start=1):
                        cv2.putText(larger, line,
                                    (10, offset + i * line_height), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            else:
                # Show new window with cropped image and data
                right, bottom = max(0, target_w - self.cropped.shape[1]), \
                                max(0, target_h - self.cropped.shape[0])

                larger = cv2.copyMakeBorder(self.cropped, top, bottom, left, right, cv2.BORDER_CONSTANT, None, (0, 0, 0))

                cv2.putText(larger, "Input",
                            (10, offset + 0 * line_height), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            cv2.imshow("Data input", larger)


if __name__ == "__main__":
    """
        Possible trackers:
            csrt, kcf, boosting, mil, tld, medianflow, mosse
    """
    tracker = ScreenTracker(tracker="csrt")
    tracker.start()
