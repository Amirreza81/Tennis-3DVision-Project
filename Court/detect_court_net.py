import cv2
from enum import IntEnum
import os
import logging
from black import assert_equivalent
from chardet import detect
import numpy as np
import matplotlib.pyplot as plt
from skimage.measure import LineModelND, ransac


class TennisCourtLine:
    def __init__(self, line_pixels, image_shape) -> None:
        self._line_pixels = line_pixels

        # Fit a line to the data in the form a * row + b * column + c = 0
        A = np.column_stack((line_pixels, np.ones(line_pixels.shape[0])))
        U, s, VT = np.linalg.svd(A)
        self.line = VT[-1, :]

        if len(image_shape) == 2:
            self._rows, self._columns = image_shape
        else:
            self._rows, self._columns, _ = image_shape

        self._image_intersection_points = self.find_image_intersection_points()

        p1, p2 = self._image_intersection_points
        self._angle = np.arctan2(np.abs(p1[0] - p2[0]), np.abs(p1[1] - p2[1])) * 180.0 / np.pi
        self.horizontal = self._angle <= 7.5
        self.midpoint = np.mean(line_pixels, axis=0)

    #     def __repr__(self) -> str:
    #         return '{' + \
    #                     f'Angle={self._angle} ' + \
    #                     f'Intersection Points={self._image_intersection_points}, ' + \
    #                     f'Midpoint={self.midpoint}' + \
    #                 '}'

    def find_image_intersection_points(self):
        a, b, c = self.line
        # when on the left side of the image
        left_intersection = (round(-c / a), 0)
        # when on the right side of the image
        right_intersection = (round((-c - b * (self._columns - 1)) / a), self._columns - 1)

        # when on the top of the iamge
        top_intersection = (0, round(-c / b))
        # when when on the bottom of the image
        bottom_intersection = (self._rows - 1, round((-c - a * (self._rows - 1)) / b))

        # only 2 of these 4 points can be within the image
        intersection = []
        if 0 <= left_intersection[0] <= self._rows - 1:
            intersection.append(left_intersection)
        if 0 <= right_intersection[0] <= self._rows - 1:
            intersection.append(right_intersection)
        if 0 <= top_intersection[1] <= self._columns - 1:
            intersection.append(top_intersection)
        if 0 <= bottom_intersection[1] <= self._columns - 1:
            intersection.append(bottom_intersection)

        # logging.debug(f'Intersection point for tennis court line: {intersection[:2]}')

        return intersection[:2]

    def intersection(self, tennis_court_line):
        p = np.cross(self.line, tennis_court_line.line)
        p /= p[-1]
        return np.round(p[:2]).astype(np.uint64)

    def endpoints_between_points(self, p1, p2):
        line_points = self._line_pixels.copy()
        if self.horizontal:
            line_points = np.array(list(filter(lambda x: x[1] >= p1[1], line_points)))
            line_points = np.array(list(filter(lambda x: x[1] <= p2[1], line_points)))
        else:
            line_points = np.array(list(filter(lambda x: x[0] >= p1[0], line_points)))
            line_points = np.array(list(filter(lambda x: x[0] <= p2[0], line_points)))

        endpoints = []
        index = 1 if self.horizontal else 0
        min_endpoint_index = np.argmin(line_points[:, index])
        max_endpoint_index = np.argmax(line_points[:, index])
        endpoints.append(line_points[min_endpoint_index])
        endpoints.append(line_points[max_endpoint_index])
        return np.array(endpoints)

    def draw_line_on_image(self, image, color=(0, 0, 0), thickness=3):
        p1, p2 = self._image_intersection_points
        return cv2.line(image, (p1[1], p1[0]), (p2[1], p2[0]), color, thickness)


class TennisCourt:
    class LineID(IntEnum):
        CLOSE_BASELINE = 0
        CLOSE_SERVICE_LINE = 1
        NET_LINE = 2
        FAR_SERVICE_LINE = 3
        FAR_BASELINE = 4
        LEFT_DOUBLES_LINE = 5
        LEFT_SINGLES_LINE = 6
        RIGHT_DOUBLES_LINE = 7
        RIGHT_SINGLES_LINE = 8
        CENTER_SERVICE_LINE = 9
        NUMBER_OF_LINES = 10

    class KeypointID(IntEnum):
        # Intersection keypoints
        CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE = 0
        CLOSE_BASELINE_AND_LEFT_SINGLES_LINE = 1
        CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE = 2
        CLOSE_BASELINE_AND_RIGHT_SINGLES_LINE = 3
        CLOSE_SERVICE_LINE_AND_LEFT_SINGLES_LINE = 4
        CLOSE_SERVICE_LINE_AND_CENTER_SERVICE_LINE = 5
        CLOSE_SERVICE_LINE_AND_RIGHT_SINGLES_LINE = 6
        FAR_BASELINE_AND_LEFT_DOUBLES_LINE = 7
        FAR_BASELINE_AND_LEFT_SINGLES_LINE = 8
        FAR_BASELINE_AND_RIGHT_DOUBLES_LINE = 9
        FAR_BASELINE_AND_RIGHT_SINGLES_LINE = 10
        FAR_SERVICE_LINE_AND_LEFT_SINGLES_LINE = 11
        FAR_SERVICE_LINE_AND_CENTER_SERVICE_LINE = 12
        FAR_SERVICE_LINE_AND_RIGHT_SINGLES_LINE = 13
        NET_LINE_AND_CENTER_SERVICE_LINE = 14

        # Net line keypoints using endpoints
        NET_LINE_LEFT_ENDPOINT = 15
        NET_LINE_RIGHT_ENDPOINT = 16

    INTERSECTION_KEYPOINT_PAIRS = {
        KeypointID.CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE: (LineID.CLOSE_BASELINE, LineID.LEFT_DOUBLES_LINE),
        KeypointID.CLOSE_BASELINE_AND_LEFT_SINGLES_LINE: (LineID.CLOSE_BASELINE, LineID.LEFT_SINGLES_LINE),
        KeypointID.CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE: (LineID.CLOSE_BASELINE, LineID.RIGHT_DOUBLES_LINE),
        KeypointID.CLOSE_BASELINE_AND_RIGHT_SINGLES_LINE: (LineID.CLOSE_BASELINE, LineID.RIGHT_SINGLES_LINE),
        KeypointID.CLOSE_SERVICE_LINE_AND_LEFT_SINGLES_LINE: (LineID.CLOSE_SERVICE_LINE, LineID.LEFT_SINGLES_LINE),
        KeypointID.CLOSE_SERVICE_LINE_AND_CENTER_SERVICE_LINE: (LineID.CLOSE_SERVICE_LINE, LineID.CENTER_SERVICE_LINE),
        KeypointID.CLOSE_SERVICE_LINE_AND_RIGHT_SINGLES_LINE: (LineID.CLOSE_SERVICE_LINE, LineID.RIGHT_SINGLES_LINE),
        KeypointID.FAR_BASELINE_AND_LEFT_DOUBLES_LINE: (LineID.FAR_BASELINE, LineID.LEFT_DOUBLES_LINE),
        KeypointID.FAR_BASELINE_AND_LEFT_SINGLES_LINE: (LineID.FAR_BASELINE, LineID.LEFT_SINGLES_LINE),
        KeypointID.FAR_BASELINE_AND_RIGHT_DOUBLES_LINE: (LineID.FAR_BASELINE, LineID.RIGHT_DOUBLES_LINE),
        KeypointID.FAR_BASELINE_AND_RIGHT_SINGLES_LINE: (LineID.FAR_BASELINE, LineID.RIGHT_SINGLES_LINE),
        KeypointID.FAR_SERVICE_LINE_AND_LEFT_SINGLES_LINE: (LineID.FAR_SERVICE_LINE, LineID.LEFT_SINGLES_LINE),
        KeypointID.FAR_SERVICE_LINE_AND_CENTER_SERVICE_LINE: (LineID.FAR_SERVICE_LINE, LineID.CENTER_SERVICE_LINE),
        KeypointID.FAR_SERVICE_LINE_AND_RIGHT_SINGLES_LINE: (LineID.FAR_SERVICE_LINE, LineID.RIGHT_SINGLES_LINE),
        KeypointID.NET_LINE_AND_CENTER_SERVICE_LINE: (LineID.NET_LINE, LineID.CENTER_SERVICE_LINE),
    }

    DRAW_COURT_KEYPOINT_PAIRS = [
        (KeypointID.CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE, KeypointID.CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE),
        (KeypointID.FAR_BASELINE_AND_LEFT_DOUBLES_LINE, KeypointID.FAR_BASELINE_AND_RIGHT_DOUBLES_LINE),
        (KeypointID.CLOSE_SERVICE_LINE_AND_LEFT_SINGLES_LINE, KeypointID.CLOSE_SERVICE_LINE_AND_RIGHT_SINGLES_LINE),
        (KeypointID.FAR_SERVICE_LINE_AND_LEFT_SINGLES_LINE, KeypointID.FAR_SERVICE_LINE_AND_RIGHT_SINGLES_LINE),
        (KeypointID.CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE, KeypointID.FAR_BASELINE_AND_LEFT_DOUBLES_LINE),
        (KeypointID.CLOSE_BASELINE_AND_LEFT_SINGLES_LINE, KeypointID.FAR_BASELINE_AND_LEFT_SINGLES_LINE),
        (KeypointID.CLOSE_SERVICE_LINE_AND_CENTER_SERVICE_LINE, KeypointID.FAR_SERVICE_LINE_AND_CENTER_SERVICE_LINE),
        (KeypointID.CLOSE_BASELINE_AND_RIGHT_SINGLES_LINE, KeypointID.FAR_BASELINE_AND_RIGHT_SINGLES_LINE),
        (KeypointID.CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE, KeypointID.FAR_BASELINE_AND_RIGHT_DOUBLES_LINE)
    ]

    KEYPOINT_WORLD_COORDINATES = {
        KeypointID.CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE: np.array([0.0, 0.0, 0.0]),
        KeypointID.FAR_BASELINE_AND_LEFT_DOUBLES_LINE: np.array([23.77, 0.0, 0.0]),
        KeypointID.FAR_BASELINE_AND_RIGHT_DOUBLES_LINE: np.array([23.77, 10.97, 0.0]),
        KeypointID.CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE: np.array([0, 10.97, 0]),
        KeypointID.NET_LINE_LEFT_ENDPOINT: np.array([11.885, 0.91, 1.07]),
        KeypointID.NET_LINE_RIGHT_ENDPOINT: np.array([11.885, 10.51, 1.07]),
    }

    def __init__(self, image_shape, return_matrix=False) -> None:
        self._image = None
        self._image_shape = image_shape
        self._rows, self._columns, _ = image_shape
        self._court_lines = {}
        self._court_keypoints = {}
        self._court_keypoints_populated = False
        self.court_detected = False
        self.return_matrix = return_matrix


        self.M = np.zeros((3, 4))

    def detect_court(self, court_image) -> bool:
        assert court_image.shape == self._image_shape
        self._image = court_image.copy()
        image = court_image

        # Step 1. Mask out all colors that are not the colors of the court lines (white)
        white_pixel_boundaries = np.array([[150, 150, 150], [255, 255, 255]])
        white_mask = cv2.inRange(image, white_pixel_boundaries[0], white_pixel_boundaries[1])
        image = cv2.bitwise_and(image, image, mask=white_mask)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)[1]

        # Step 2. Cut out all the detected white pixels that are not near the center of the image
        cut_columns_boundary = np.round([0.10 * self._columns, 0.8 * self._columns]).astype(np.uint64)
        image[:, :cut_columns_boundary[0]] = 0
        image[:, cut_columns_boundary[1]:] = 0

        cut_rows_boundary = np.round([0.10 * self._rows, 0.8 * self._rows]).astype(np.uint64)
        image[:cut_rows_boundary[0], :] = 0
        image[cut_rows_boundary[1]:, :] = 0

        # Step 3. Remove white pixels that are not part of a line of width tau
        tau_up_down, tau_left_right = (5, 5)
        image_copy = image.copy()
        for r in range(self._rows):
            for c in range(self._columns):
                if image[r, c] > 0:
                    left = max(0, c - tau_left_right)
                    right = min(self._columns - 1, c + tau_left_right)
                    up = max(0, r - tau_up_down)
                    down = min(self._rows - 1, r + tau_up_down)

                    # Need both up/down to be non-white or right/left to be non-white, but not both
                    left_right_non_white = image[r, left] == 0 and image[r, right] == 0
                    up_down_non_white = image[up, c] == 0 and image[down, c] == 0
                    if left_right_non_white == up_down_non_white:
                        image_copy[r, c] = 0
        image = image_copy

        # Step 4. Run RANSAC to detect the 9 court lines and the net line
        tau = max(tau_up_down, tau_left_right)
        white_pixels = np.where(image > 0)
        white_pixels = np.column_stack((white_pixels[0], white_pixels[1]))
        court_lines = []
        for _ in range(TennisCourt.LineID.NUMBER_OF_LINES):
            model_robust, inliers = ransac(white_pixels, LineModelND, min_samples=2, residual_threshold=tau,
                                           max_trials=1000)

            line = np.array(white_pixels[inliers])
            white_pixels = np.array(white_pixels[[not inlier for inlier in inliers]])

            court_line = TennisCourtLine(line, self._image_shape)
            court_lines.append(court_line)
            # logging.debug(f'Found line {court_line}')


        original_image_copy = court_image.copy()
        for line in court_lines:
            original_image_copy = line.draw_line_on_image(original_image_copy)

        # Step 5. Identify each of the lines by comparing their mid-points
        horizontal_court_lines = []
        vertical_court_lines = []
        for court_line in court_lines:
            if court_line.horizontal:
                horizontal_court_lines.append(court_line)
            else:
                vertical_court_lines.append(court_line)

        if len(horizontal_court_lines) != 5 or len(vertical_court_lines) != 5:
            logging.debug(
                f'{len(horizontal_court_lines)} horizontal lines detected, {len(vertical_court_lines)} vertical lines detected, needed 5 of each')
            self.court_detected = False
            return self.court_detected

        # Sort horizontal court lines by their midpoint row
        horizontal_court_lines = sorted(horizontal_court_lines, key=lambda x: x.midpoint[0])
        horizontal_line_order = [
            TennisCourt.LineID.FAR_BASELINE.value,
            TennisCourt.LineID.FAR_SERVICE_LINE.value,
            TennisCourt.LineID.NET_LINE.value,
            TennisCourt.LineID.CLOSE_SERVICE_LINE.value,
            TennisCourt.LineID.CLOSE_BASELINE.value,
        ]
        for line, id in zip(horizontal_court_lines, horizontal_line_order):
            self._court_lines[id] = line

        # Sort vertical court lines by their midpoint column
        vertical_court_lines = sorted(vertical_court_lines, key=lambda x: x.midpoint[1])
        vertical_line_order = [
            TennisCourt.LineID.LEFT_DOUBLES_LINE.value,
            TennisCourt.LineID.LEFT_SINGLES_LINE.value,
            TennisCourt.LineID.CENTER_SERVICE_LINE.value,
            TennisCourt.LineID.RIGHT_SINGLES_LINE.value,
            TennisCourt.LineID.RIGHT_DOUBLES_LINE.value,
        ]
        for line, id in zip(vertical_court_lines, vertical_line_order):
            self._court_lines[id] = line

        # Step 6. Find the intersections to get the keypoints
        list_of_keypoints = []
        for intersection in TennisCourt.INTERSECTION_KEYPOINT_PAIRS:
            intersection_id = intersection.value
            l1_id, l2_id = TennisCourt.INTERSECTION_KEYPOINT_PAIRS[intersection_id]
            intersection_pixel = self._court_lines[l1_id].intersection(self._court_lines[l2_id])

            # Do a running average on the keypoints
            if not self._court_keypoints_populated:
                self._court_keypoints[intersection_id] = intersection_pixel
            else:
                alpha = 0.5
                self._court_keypoints[intersection_id] = alpha * intersection_pixel + (1 - alpha) * \
                                                         self._court_keypoints[intersection_id]

            # logging.debug(f'{intersection.name} == {intersection_pixel}')
            list_of_keypoints.append(list(intersection_pixel))

        self._court_keypoints_populated = True

        # Step 7. Net line endpoints that lie within the court are also keypoints
        left_doubles_line_midpoint = self._court_lines[TennisCourt.LineID.LEFT_DOUBLES_LINE].midpoint
        right_doubles_line_midpoint = self._court_lines[TennisCourt.LineID.RIGHT_DOUBLES_LINE].midpoint
        net_line_endpoints = self._court_lines[TennisCourt.LineID.NET_LINE].endpoints_between_points(
            left_doubles_line_midpoint, right_doubles_line_midpoint)
        # logging.debug(f'Net line endpoints: {net_line_endpoints}')
        net_points = []
        net_points.append(list(net_line_endpoints[0]))
        net_points.append(list(net_line_endpoints[1]))
        self._court_keypoints[TennisCourt.KeypointID.NET_LINE_LEFT_ENDPOINT] = net_line_endpoints[0]
        self._court_keypoints[TennisCourt.KeypointID.NET_LINE_RIGHT_ENDPOINT] = net_line_endpoints[1]
        self.court_detected = True
        original_image_copy = self.draw_detected_keypoints()
        detected_court = self.draw_detected_court()
        # cv2.imshow("detect_court", detected_court)
        # cv2.waitKey(0)
        if self.return_matrix:
            return detected_court
        return list_of_keypoints, net_points

    def calibrate(self):
        keypoint_ordering = [
            TennisCourt.KeypointID.CLOSE_BASELINE_AND_LEFT_DOUBLES_LINE,
            TennisCourt.KeypointID.FAR_BASELINE_AND_LEFT_DOUBLES_LINE,
            TennisCourt.KeypointID.FAR_BASELINE_AND_RIGHT_DOUBLES_LINE,
            TennisCourt.KeypointID.CLOSE_BASELINE_AND_RIGHT_DOUBLES_LINE,
            TennisCourt.KeypointID.NET_LINE_LEFT_ENDPOINT,
            TennisCourt.KeypointID.NET_LINE_RIGHT_ENDPOINT,
        ]

        image_coordinates = np.zeros((len(keypoint_ordering), 2))
        world_coordinates = np.zeros((len(keypoint_ordering), 3))
        for i, keypoint in enumerate(keypoint_ordering):
            image_coordinates[i, :] = self._court_keypoints[keypoint]
            world_coordinates[i, :] = self.KEYPOINT_WORLD_COORDINATES[keypoint]

        self.M = TennisCourt.calibrate_camera(image_coordinates, world_coordinates)

    @staticmethod
    def calibrate_camera(image_coordinates, world_coordinates):
        points = image_coordinates.shape[0]
        image_coordinates_homogeneous = np.column_stack((image_coordinates, np.ones(points)))
        world_coordinates_homogeneous = np.column_stack((world_coordinates, np.ones(points)))

        P = np.zeros((points * 2, 12))
        for i in range(points):
            world_coordinate = world_coordinates_homogeneous[i, :]
            image_coordinate = image_coordinates_homogeneous[i, :]
            P[i * 2, :4] = world_coordinate
            P[i * 2, 8:] = -image_coordinate[0] * world_coordinate
            P[i * 2 + 1, 4:8] = world_coordinate
            P[i * 2 + 1, 8:] = -image_coordinate[1] * world_coordinate

        U, s, VT = np.linalg.svd(P)
        m = VT[-1, :]
        M = m.reshape((3, 4))
        logging.debug(f'Calibrated camera matrix M = {M}')
        return M

    def draw_detected_keypoints(self, image=None):
        if not self._court_keypoints_populated:
            return None

        if image is None:
            image = self._image.copy()

        for intersection_id in self._court_keypoints:
            row, col = np.round(self._court_keypoints[intersection_id]).astype(np.uint64)
            image = cv2.circle(image, center=(col, row), radius=5, color=(0, 0, 255), thickness=-1)
        return image

    def draw_detected_court(self, image=None):
        if image is None:
            image = self._image.copy()

        if not self._court_keypoints_populated:
            return image

        for p1_id, p2_id in TennisCourt.DRAW_COURT_KEYPOINT_PAIRS:
            p1 = np.round(self._court_keypoints[p1_id]).astype(np.uint64)
            p2 = np.round(self._court_keypoints[p2_id]).astype(np.uint64)
            image = cv2.line(image, (p1[1], p1[0]), (p2[1], p2[0]), color=(0, 0, 0), thickness=3)

        p1 = self._court_keypoints[TennisCourt.KeypointID.NET_LINE_LEFT_ENDPOINT]
        p2 = self._court_keypoints[TennisCourt.KeypointID.NET_LINE_RIGHT_ENDPOINT]
        image = cv2.line(image, (p1[1], p1[0]), (p2[1], p2[0]), color=(0, 255, 0), thickness=3)

        image = self.draw_detected_keypoints(image)

        return image

def detect_points(image, return_matrix=False):
    tennis_court = TennisCourt(image.shape, return_matrix)
    return tennis_court.detect_court(image)

# Example:
# image = cv2.imread("tennis15.jpeg")
# print(detect_points(image, True))
