from screentracker import ScreenTracker, HandlerData
from bits import Bits
from colours import *

import numpy as np
import cv2
from bitarray import bitarray
import sys
import itertools
import math


def is_ascending(li):
    if isinstance(li, (list, tuple)):
        li_type = type(li)
    else:
        li_type = tuple
        li = li_type(li)
    return li_type(sorted(li)) == li


class Detector:
    MODES = {
        0: "Single screen",
        1: "Clock-Data",
        2: "Brightness modulation"
    }

    def __init__(self, mode=0, true_ratio=0.5, start_bits=bitarray("110011"),
                       stop_bytes=b"\n", window_size=2, window_positive=2,
                       brighness_levels=4, bright_dev_percent=0.4, brighness_w_clk=False):
        super().__init__()

        self.mode = mode if mode in Detector.MODES else 1
        self._mode_callback = {
            0: self._mode_single,
            1: self._mode_clk_data,
            2: self._mode_brightness_mod,
        }

        self.true_ratio = true_ratio or 0.5
        self.start_bits = start_bits if isinstance(start_bits, bitarray) else bitarray(start_bits)
        self.stop_bytes = stop_bytes or b"\n"
        self.data       = bitarray()
        self.buffer     = bitarray()

        self.received  = [b""]
        self.got_start = False

        self.prev_clk = False

        self.value_size  = window_positive  # Least amount of values in window that need to be True to count as '1'
        self.window_size = window_size      # Amount of values to process before determining one bit
        self.capturing_window = False

        self.levels = brighness_levels
        self.bright_dev_percent = bright_dev_percent
        self.brightness_levels  = tuple()
        self.brightness_values  = {}
        self.brighness_w_clk    = brighness_w_clk
        self._prepare_brightness_levels()

        self.ct, self.dt = bitarray(), bitarray()


    def _log(self, msg):
        print(style("[Detector]", Colours.FG.YELLOW), msg)

    def reset(self):
        self.data   = bitarray()
        self.buffer = bitarray()
        self.received = [b""]
        self.got_start = False

    def determine_bits(self, frame):
        return self._mode_callback[self.mode](frame)

    def _filter_bin_threshold(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5,5), 0)
        ret, filtered = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return filtered if ret else frame

    def _prepare_brightness_levels(self):
        deviation = 255 / (self.levels - 1) * self.bright_dev_percent
        ranges = []

        for primary in (int(255 / (self.levels - 1) * i) for i in range(self.levels)):
            lower, upper = primary - deviation, primary + deviation
            ranges.append(max(lower, 0))
            ranges.append(min(upper, 255))

        self.brightness_levels = tuple(ranges)

        bits = int(math.ceil(math.log(self.levels, 2)))
        self.brightness_values = { i: p for i, p in enumerate(itertools.product((False, True), repeat=bits)) }

        if not is_ascending(self.brightness_values):
            raise Exception(f"Brightness values overlap! Decrease levels ({self.levels}) " + \
                            f"or decrease deviation percentage ({self.self.bright_dev_percent})!")

    def _filter_brightness(self, frame, lvl=0):
        """
            deviation_percentage = 0.1
            deviation = 255 / lvls * deviation_percentage

            lvls = 2:  [0, 128, 255]
                    => [0, deviation, 128-deviation, 128+deviation, 255-deviation, 255]

            lvls = 3:  [0,  84, 170, 255]
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Extra crop
        h, w = gray.shape
        y, x = int(h*0.2), int(w*0.2)
        gray = gray[y:h-y, x:w-x]  # .copy()

        blur = cv2.GaussianBlur(gray, (5,5), 0)

        level_check = []
        average = np.average(blur)

        # Loop and check if between threshold
        for i in range(0, len(self.brightness_levels), 2):
            lower, upper = self.brightness_levels[i], self.brightness_levels[i+1]
            # level_check.append(((lower <= blur) & (blur <= upper)).sum())
            level_check.append(lower <= average <= upper)

        return blur, np.array(level_check)


        # Test
        # lower, upper = self.brightness_levels[lvl * 2], \
        #                self.brightness_levels[lvl * 2 + 1]
        # mask = cv2.inRange(blur, lower, upper)
        # res  = cv2.bitwise_and(frame, frame, mask=mask)

        # return res


    def _mode_single(self, frame):
        # Callback gets called 16 times per second (16 fps limit)
        # Acquisition rate should be twice the input,s
        # thus check the frame twice and if both have the same result,
        # use that value.
        # Max transmission rate is 8 bits per second, or 1 byte/char per second.

        ret = HandlerData()

        frame = self._filter_bin_threshold(frame)
        ret.add_screen("Screen", frame)

        # whites = np.where(frame >= 128)
        whites = (frame >= 128).sum()
        ratio  = whites / frame.size

        self.buffer.append(ratio >= self.true_ratio)
        length, start_length = self.buffer.length(), self.start_bits.length()

        if not self.got_start:
            if length >= start_length:
                try:
                    self._log(self.buffer.to01())
                    idx = self.buffer.to01().index(self.start_bits.to01())
                except ValueError:
                    self.got_start = False
                else:
                    self._log(f"Got start bits, receiving until {self.stop_bytes}...")
                    self.buffer    = self.buffer[idx + start_length:]
                    length         = self.buffer.length()
                    self.got_start = True

        if self.got_start:
            while length >= self.window_size:
                # Slice window out of buffer
                window, self.buffer = self.buffer[0:self.window_size], self.buffer[self.window_size:]
                length = self.buffer.length()

                # Count amount of True/False bits in window
                positive = window.count(True)
                # negative = self.window_size - positive

                # On self.window_size received 0/1 bits, append 0/1 bit to data
                self.data.append(positive >= self.value_size)

                if self.data.length() % 8 == 0:
                    # Got at least 1 full byte
                    bytestr = self.data.tobytes()
                    self.received[-1] = bytestr

                    self._log(f"Got: {self.data[-8:].to01()} => ({len(bytestr)}) {bytestr}")

                    if bytestr.endswith(self.stop_bytes):
                        # Remove stop bytes
                        bytestr = bytestr[0:-len(self.stop_bytes)]
                        bytestr = str(Bits.bytes_to_str(bytestr))
                        self.received[-1] = bytestr

                        self._log(f"Completed: {bytestr}")
                        self._log("Reset...")
                        self.data = bitarray()
                        self.received.append(b"")
                        self.got_start = False

        ret.add_info(f"Data: {int(ratio * 100)}% white, Found start bits? {self.got_start}")
        for d in self.received:
            ret.add_info(str(d))
        return ret

    def _mode_clk_data(self, frame):
        ret = HandlerData()

        frame = self._filter_bin_threshold(frame)

        # Orient to portrait
        h, w  = frame.shape

        if w > h:
            # Turn 90°
            frame = np.rot90(frame, axes=(1,0))
            h, w = w, h

        # Divide frame in top (clock) and bottom (data)
        half = h // 2

        frame_clock = frame[0:half, 0:w]
        frame_data  = frame[half:half*2, 0:w]

        ret.add_screen("Clock", frame_clock)
        ret.add_screen("Data", frame_data)

        clk, data = (frame_clock >= 128).sum(), (frame_data >= 128).sum()
        clk, data = clk / frame_clock.size, data / frame_data.size
        clk, data = clk >= self.true_ratio, data >= self.true_ratio

        # self.ct.append(clk)
        # self.dt.append(data)
        # print(f"c: {self.ct.to01()}\nd: {self.dt.to01()}")

        if self.prev_clk != clk:
            self.prev_clk = clk
            self.capturing_window = True

            ret.add_info(f"clk={clk}, data={data}, Found start bits? {self.got_start}")
            for d in self.received:
                ret.add_info(str(d))
            return ret

        if self.capturing_window:
            self.data.append(data)
        self.capturing_window = False

        if not self.got_start:
            start_length = self.start_bits.length()

            if self.data.length() >= start_length:
                try:
                    self._log(self.data.to01())
                    idx = self.data.to01().index(self.start_bits.to01())
                except ValueError:
                    self.got_start = False
                else:
                    self._log(f"Got start bits, receiving until {self.stop_bytes}...")
                    self.data      = self.data[idx + start_length:]
                    self.got_start = True

        elif self.got_start:
            if self.data.length() > 0 and self.data.length() % 8 == 0:
                # Got at least 1 full byte
                bytestr = self.data.tobytes()

                if len(self.received[-1]) != len(bytestr):
                    self._log(f"Got: {self.data[-8:].to01()} => ({len(bytestr)}) {bytestr}")

                self.received[-1] = bytestr

                if bytestr.endswith(self.stop_bytes):
                    # Remove stop bytes
                    bytestr = bytestr[0:-len(self.stop_bytes)]
                    bytestr = str(Bits.bytes_to_str(bytestr))
                    self.received[-1] = bytestr

                    self._log(f"Completed: {bytestr}")
                    self._log("Reset...")
                    self.data = bitarray()
                    self.received.append(b"")
                    self.got_start = False


        ret.add_info(f"clk={clk}, data={data}, Found start bits? {self.got_start}")
        for d in self.received:
            ret.add_info(str(d))
        return ret

    def _mode_brightness_mod(self, frame):
        ret = HandlerData()

        frame, levels = self._filter_brightness(frame)

        ret.add_screen("View", frame)
        ret.add_info(f"Levels={list(levels)}")

        # Get highest level
        max_level = np.argmax(levels)

        # Get values for specific level
        data = self.brightness_values[max_level]
        ret.add_info(f"Values={data}, Found start bits? {self.got_start}")

        if self.brighness_w_clk:
            clk, data = data[0], data[1:]

            if self.prev_clk != clk:
                self.prev_clk = clk
                self.data.extend(data)
        else:
            self.data.extend(data)

        if not self.got_start:
            start_length = self.start_bits.length()

            if self.data.length() >= start_length:
                try:
                    self._log(self.data.to01())
                    idx = self.data.to01().index(self.start_bits.to01())
                except ValueError:
                    self.got_start = False
                else:
                    self._log(f"Got start bits, receiving until {self.stop_bytes}...")
                    self.data      = self.data[idx + start_length:]
                    self.got_start = True

        if self.got_start:
            if self.data.length() > 0 and self.data.length() % 8 == 0:
                # Got at least 1 full byte
                bytestr = self.data.tobytes()

                if len(self.received[-1]) != len(bytestr):
                    self._log(f"Got: {self.data[-8:].to01()} => ({len(bytestr)}) {bytestr}")

                self.received[-1] = bytestr

                if bytestr.endswith(self.stop_bytes):
                    # Remove stop bytes
                    bytestr = bytestr[0:-len(self.stop_bytes)]
                    bytestr = str(Bits.bytes_to_str(bytestr))
                    self.received[-1] = bytestr

                    self._log(f"Completed: {bytestr}")
                    self._log("Reset...")
                    self.data = bitarray()
                    self.received.append(b"")
                    self.got_start = False

        for d in self.received:
            ret.add_info(str(d))
        return ret

if __name__ == "__main__":
    mode, start_bits, brightness_clk, fps_limit = 3, "11110011", False, 60

    if len(sys.argv) > 2 and sys.argv[1] in ("-m", "--mode"):
        mode = int(sys.argv[2])

    if mode == 0:
        # Single screen
        fps_limit  = 8
        start_bits = "111100001111"
    elif mode == 1:
        # 2 sections: clk and data
        pass
    elif mode == 2:
        # Brightness modulation, without clock
        fps_limit      = 8
        brightness_clk = False
        start_bits     = "111100001111"
    elif mode == 3:
        # Brightness modulation, with clock
        mode = 2
        brightness_clk = True

    d = Detector(mode=mode, start_bits=start_bits, brighness_w_clk=brightness_clk)
    tracker = ScreenTracker(input_callback=d.determine_bits, reset_callback=d.reset, tracker="static", fps_limit=fps_limit)
    tracker.start()
