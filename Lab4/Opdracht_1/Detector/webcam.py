import numpy as np
import cv2


class Webcam:
    def __init__(self, show_frame=True, destroy_windows=True, exit_key='q'):
        super().__init__()
        self.show            = show_frame
        self.destroy_windows = destroy_windows

        self._cap      = None
        self._exit_key = exit_key

    def __del__(self):
        if self._cap:
            self._cap.release()
        if self.destroy_windows:
            cv2.destroyAllWindows()

    def __str__(self):
        return f"<Webcam {self.width}x{self.height}@{self.fps}>"

    @property
    def width(self):
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0

    @width.setter
    def width(self, value):
        if self._cap and value > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, value)

    @property
    def height(self):
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0

    @height.setter
    def height(self, value):
        if self._cap and value > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, value)

    @property
    def fps(self):
        return self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 0

    @fps.setter
    def fps(self, value):
        if self._cap and 0 < value <= 60:
            self._cap.set(cv2.CAP_PROP_FPS, value)

    @property
    def brightness(self):
        return self._cap.get(cv2.CAP_PROP_BRIGHTNESS) if self._cap else 0

    @brightness.setter
    def brightness(self, value):
        if self._cap and value > 0:
            self._cap.set(cv2.CAP_PROP_BRIGHTNESS, value)

    @property
    def contrast(self):
        return self._cap.get(cv2.CAP_PROP_CONTRAST) if self._cap else 0

    @contrast.setter
    def contrast(self, value):
        if self._cap and value > 0:
            self._cap.set(cv2.CAP_PROP_CONTRAST, value)

    @property
    def saturation(self):
        return self._cap.get(cv2.CAP_PROP_SATURATION) if self._cap else 0

    @saturation.setter
    def saturation(self, value):
        if self._cap and value > 0:
            self._cap.set(cv2.CAP_PROP_SATURATION, value)

    def set_params(self, brightness=None, contrast=None, saturation=None, fps=None):
        if brightness:
            self.brightness = brightness
        if contrast:
            self.contrast = contrast
        if saturation:
            self.saturation = saturation
        if fps:
            self.fps = fps

    def capture_start(self):
        self._cap = cv2.VideoCapture(0)  # arg cv2.CAP_DSHOW removes warning, but tanks fps...

        # self.brightness = 10

    def capture_new(self):
        if not self._cap:
            return None

        # Capture frame-by-frame
        ret, frame = self._cap.read()
        return frame if ret else None

    def capture_loop(self, callback):
        while(True):
            # Capture frame-by-frame
            frame = self.capture_new()

            if frame is not None and callback:
                callback(frame)
            else:
                break

            if cv2.waitKey(1) & 0xFF == ord(self._exit_key):
                break

    @staticmethod
    def make_grayscale(frame):
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def show_frame(frame):
        gray = Webcam.make_grayscale(frame)
        cv2.imshow('Webcam', gray)


if __name__ == "__main__":
    cam = Webcam()
    cam.capture_start()
    cam.capture_loop(Webcam.show_frame)
