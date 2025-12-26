import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable
from enum import Enum


try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


from logger import logger
from config_reader import config


class MovementStyle(Enum):
    """Different movement personality types"""
    RELAXED = "relaxed"      # Slower, smoother movements
    NORMAL = "normal"        # Average user behavior
    IMPATIENT = "impatient"  # Faster, more direct movements
    CAUTIOUS = "cautious"    # Slower with more pauses


@dataclass
class MouseState:
    """Track mouse state for continuous simulation"""
    last_move_time: float = 0.0
    total_distance_moved: float = 0.0
    click_count: int = 0
    current_style: MovementStyle = MovementStyle.NORMAL
    velocity: Tuple[float, float] = (0.0, 0.0)  # Track momentum
    fatigue_level: float = 0.0  # Increases over time, affects precision


class EasingFunctions:
    """Physics-based easing for natural movement"""

    @staticmethod
    def ease_out_expo(t: float) -> float:
        """Exponential ease out - fast start, slow end"""
        return 1 - math.pow(2, -10 * t) if t < 1 else 1

    @staticmethod
    def ease_in_out_cubic(t: float) -> float:
        """Cubic ease in-out"""
        if t < 0.5:
            return 4 * t * t * t
        return 1 - math.pow(-2 * t + 2, 3) / 2

    @staticmethod
    def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
        """Ease out with slight overshoot - mimics natural stopping"""
        return 1 + (overshoot + 1) * math.pow(t - 1, 3) + overshoot * math.pow(t - 1, 2)

    @staticmethod
    def ease_with_hesitation(t: float) -> float:
        """Adds a slight hesitation mid-movement"""
        if t < 0.3:
            return EasingFunctions.ease_in_out_cubic(t / 0.3) * 0.3
        elif t < 0.4:
            # Slight pause/slowdown
            return 0.3 + (t - 0.3) * 0.5
        else:
            return 0.35 + EasingFunctions.ease_out_expo((t - 0.4) / 0.6) * 0.65

    @staticmethod
    def random_easing() -> Callable[[float], float]:
        """Select a random easing function for variety"""
        easings = [
            EasingFunctions.ease_out_expo,
            EasingFunctions.ease_in_out_cubic,
            lambda t: EasingFunctions.ease_out_back(t, random.uniform(1.2, 2.0)),
            EasingFunctions.ease_with_hesitation,
        ]
        weights = [0.3, 0.35, 0.15, 0.2]
        return random.choices(easings, weights=weights)[0]


class BezierCurve:
    """Generate bezier curve paths for natural mouse movement"""

    @staticmethod
    def quadratic(t: float, p0: Tuple[float, float], p1: Tuple[float, float],
                  p2: Tuple[float, float]) -> Tuple[float, float]:
        """Calculate point on quadratic bezier curve at parameter t"""
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        return (x, y)

    @staticmethod
    def cubic(t: float, p0: Tuple[float, float], p1: Tuple[float, float],
              p2: Tuple[float, float], p3: Tuple[float, float]) -> Tuple[float, float]:
        """Calculate point on cubic bezier curve at parameter t"""
        x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] +
             3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0])
        y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] +
             3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1])
        return (x, y)

    @staticmethod
    def generate_control_points(start: Tuple[float, float], end: Tuple[float, float],
                                curvature: float = 0.3,
                                previous_velocity: Tuple[float, float] = None) -> List[Tuple[float, float]]:
        """Generate control points for a natural-looking bezier curve

        Args:
            start: Starting point (x, y)
            end: Ending point (x, y)
            curvature: How much the curve deviates from straight line (0-1)
            previous_velocity: Previous movement direction for momentum continuity

        Returns:
            List of control points for cubic bezier curve
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx ** 2 + dy ** 2)

        # Perpendicular offset for curve
        offset_magnitude = distance * curvature * random.uniform(0.5, 1.5)

        # Use previous velocity for momentum if available
        if previous_velocity and (previous_velocity[0] != 0 or previous_velocity[1] != 0):
            # Blend previous direction with new direction
            prev_angle = math.atan2(previous_velocity[1], previous_velocity[0])
            new_angle = math.atan2(dy, dx)

            # First control point influenced by previous momentum
            momentum_factor = random.uniform(0.2, 0.5)
            cp1_x = start[0] + math.cos(prev_angle) * distance * momentum_factor * 0.3
            cp1_y = start[1] + math.sin(prev_angle) * distance * momentum_factor * 0.3
            cp1 = (cp1_x, cp1_y)
        else:
            # Random direction for curve (left or right of straight line)
            perpendicular_angle = math.atan2(dy, dx) + math.pi / 2
            if random.random() > 0.5:
                perpendicular_angle += math.pi

            # Control point 1 - closer to start
            t1 = random.uniform(0.2, 0.4)
            cp1_base_x = start[0] + dx * t1
            cp1_base_y = start[1] + dy * t1
            cp1_offset = offset_magnitude * random.uniform(0.3, 0.7)
            cp1 = (
                cp1_base_x + math.cos(perpendicular_angle) * cp1_offset,
                cp1_base_y + math.sin(perpendicular_angle) * cp1_offset
            )

        # Control point 2 - closer to end (approach target smoothly)
        t2 = random.uniform(0.6, 0.8)
        cp2_base_x = start[0] + dx * t2
        cp2_base_y = start[1] + dy * t2

        # CP2 should guide toward target more directly
        approach_angle = math.atan2(end[1] - cp2_base_y, end[0] - cp2_base_x)
        cp2_offset = offset_magnitude * random.uniform(0.1, 0.4)
        cp2 = (
            cp2_base_x + math.cos(approach_angle + random.uniform(-0.3, 0.3)) * cp2_offset,
            cp2_base_y + math.sin(approach_angle + random.uniform(-0.3, 0.3)) * cp2_offset
        )

        return [start, cp1, cp2, end]


class WindMouse:
    """Wind Mouse algorithm for ultra-realistic movement

    Based on the classic WindMouse algorithm used in automation
    that simulates wind-like forces affecting cursor movement.
    """

    @staticmethod
    def generate_path(start: Tuple[float, float], end: Tuple[float, float],
                      gravity: float = 9.0, wind: float = 3.0,
                      min_wait: float = 2.0, max_wait: float = 10.0,
                      target_area: float = 8.0) -> List[Tuple[float, float]]:
        """Generate a wind-mouse path between two points

        Args:
            start: Starting position
            end: Target position
            gravity: Pull toward target
            wind: Random deviation force
            min_wait: Minimum ms between points
            max_wait: Maximum ms between points
            target_area: Size of target area for fine adjustment

        Returns:
            List of (x, y) points along the path
        """
        points = []

        current_x, current_y = start
        target_x, target_y = end

        wind_x = 0.0
        wind_y = 0.0
        velocity_x = 0.0
        velocity_y = 0.0

        while True:
            dist = math.hypot(target_x - current_x, target_y - current_y)

            if dist < 1:
                break

            # Wind force (random deviation)
            wind_x = wind_x / math.sqrt(3) + (random.random() * (wind * 2 + 1) - wind) / math.sqrt(5)
            wind_y = wind_y / math.sqrt(3) + (random.random() * (wind * 2 + 1) - wind) / math.sqrt(5)

            # Gravity force (pull toward target)
            if dist < target_area:
                # Close to target - increase precision
                grav_mult = gravity * (dist / target_area)
            else:
                grav_mult = gravity

            velocity_x += wind_x + grav_mult * (target_x - current_x) / dist
            velocity_y += wind_y + grav_mult * (target_y - current_y) / dist

            # Limit velocity
            max_velocity = max_wait
            velocity_mag = math.hypot(velocity_x, velocity_y)
            if velocity_mag > max_velocity:
                velocity_x = velocity_x / velocity_mag * max_velocity
                velocity_y = velocity_y / velocity_mag * max_velocity

            current_x += velocity_x
            current_y += velocity_y

            points.append((current_x, current_y))

            # Limit iterations
            if len(points) > 1000:
                break

        # Ensure we end at target
        points.append(end)

        return points


class HumanMouse:
    """Simulate realistic human mouse behavior"""

    def __init__(self):
        self.state = MouseState()
        self._select_movement_style()

        # Movement parameters based on style
        self._params = self._get_style_params()

        if PYAUTOGUI_AVAILABLE:
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0

    def _select_movement_style(self):
        """Randomly select a movement personality for this session"""
        styles = [
            (MovementStyle.RELAXED, 0.2),
            (MovementStyle.NORMAL, 0.5),
            (MovementStyle.IMPATIENT, 0.2),
            (MovementStyle.CAUTIOUS, 0.1),
        ]

        roll = random.random()
        cumulative = 0
        for style, probability in styles:
            cumulative += probability
            if roll <= cumulative:
                self.state.current_style = style
                break

        logger.debug(f"Selected mouse movement style: {self.state.current_style.value}")

    def _get_style_params(self) -> dict:
        """Get movement parameters based on current style"""
        params = {
            MovementStyle.RELAXED: {
                'base_speed': 0.4,
                'speed_variance': 0.15,
                'jitter_intensity': 0.3,
                'pause_probability': 0.15,
                'pause_duration': (0.1, 0.4),
                'curvature': 0.35,
                'overshoot_probability': 0.1,
                'wind_intensity': 2.0,
                'gravity': 7.0,
                'use_wind_mouse': 0.3,  # Probability of using wind mouse
            },
            MovementStyle.NORMAL: {
                'base_speed': 0.6,
                'speed_variance': 0.2,
                'jitter_intensity': 0.5,
                'pause_probability': 0.08,
                'pause_duration': (0.05, 0.2),
                'curvature': 0.25,
                'overshoot_probability': 0.15,
                'wind_intensity': 3.0,
                'gravity': 9.0,
                'use_wind_mouse': 0.4,
            },
            MovementStyle.IMPATIENT: {
                'base_speed': 0.85,
                'speed_variance': 0.25,
                'jitter_intensity': 0.7,
                'pause_probability': 0.03,
                'pause_duration': (0.02, 0.1),
                'curvature': 0.15,
                'overshoot_probability': 0.25,
                'wind_intensity': 4.0,
                'gravity': 12.0,
                'use_wind_mouse': 0.5,
            },
            MovementStyle.CAUTIOUS: {
                'base_speed': 0.35,
                'speed_variance': 0.1,
                'jitter_intensity': 0.2,
                'pause_probability': 0.2,
                'pause_duration': (0.15, 0.5),
                'curvature': 0.4,
                'overshoot_probability': 0.05,
                'wind_intensity': 1.5,
                'gravity': 6.0,
                'use_wind_mouse': 0.2,
            },
        }
        return params[self.state.current_style]

    def _add_micro_jitter(self, x: float, y: float, fatigue_factor: float = 1.0) -> Tuple[float, float]:
        """Add small random movements simulating hand tremor

        Real hands aren't perfectly steady - they have micro-tremors
        that create small imperfections in cursor position.
        Fatigue increases tremor intensity.
        """
        intensity = self._params['jitter_intensity'] * fatigue_factor

        # Use brownian motion-like jitter for more realistic tremor
        # Higher frequency for small movements
        jitter_x = random.gauss(0, intensity * 1.5)
        jitter_y = random.gauss(0, intensity * 1.5)

        # Occasional larger jerks (muscle twitch)
        if random.random() < 0.02 * fatigue_factor:
            jitter_x += random.choice([-1, 1]) * random.uniform(2, 5)
            jitter_y += random.choice([-1, 1]) * random.uniform(2, 5)

        return (x + jitter_x, y + jitter_y)

    def _calculate_duration(self, distance: float) -> float:
        """Calculate movement duration based on distance and style

        Uses Fitts's Law approximation: movement time is logarithmic
        with respect to distance.
        """
        base_speed = self._params['base_speed']
        variance = self._params['speed_variance']

        # Fitts's law inspired calculation
        # Longer distances take proportionally less additional time
        base_time = 0.1 + (math.log(distance + 1) / 10) * (1 / base_speed)

        # Add variance
        actual_time = base_time * random.uniform(1 - variance, 1 + variance)

        # Fatigue slightly slows movements
        fatigue_slowdown = 1 + self.state.fatigue_level * 0.1
        actual_time *= fatigue_slowdown

        # Clamp to reasonable bounds
        return max(0.05, min(actual_time, 2.0))

    def _update_fatigue(self, distance: float):
        """Update fatigue level based on movement"""
        # Increase fatigue with movement
        self.state.fatigue_level += distance / 10000

        # Natural recovery over time
        time_since_last = time.time() - self.state.last_move_time
        self.state.fatigue_level = max(0, self.state.fatigue_level - time_since_last * 0.01)

        # Cap fatigue
        self.state.fatigue_level = min(1.0, self.state.fatigue_level)

    def _generate_path_points(self, start: Tuple[float, float],
                               end: Tuple[float, float],
                               duration: float) -> List[Tuple[float, float, float]]:
        """Generate path points along bezier curve with timing

        Returns list of (x, y, timestamp) tuples representing the path.
        """
        # Decide whether to use WindMouse or Bezier
        use_wind = random.random() < self._params['use_wind_mouse']

        if use_wind:
            # Use WindMouse for this movement
            raw_points = WindMouse.generate_path(
                start, end,
                gravity=self._params['gravity'],
                wind=self._params['wind_intensity']
            )

            # Add timing to wind mouse points
            points = []
            for i, (px, py) in enumerate(raw_points):
                t = i / max(1, len(raw_points) - 1)
                timestamp = t * duration
                points.append((px, py, timestamp))

            return points

        # Use Bezier curve
        control_points = BezierCurve.generate_control_points(
            start, end,
            self._params['curvature'],
            self.state.velocity
        )

        # Number of steps based on distance and duration
        distance = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
        num_steps = max(10, int(distance / 5))  # At least 10 steps, more for longer distances

        # Select easing function
        easing_func = EasingFunctions.random_easing()

        points = []

        for i in range(num_steps + 1):
            t = i / num_steps

            # Apply easing
            t_eased = easing_func(t)

            # Get point on bezier curve
            point = BezierCurve.cubic(t_eased, *control_points)

            # Add micro-jitter (less at start and end for precision)
            jitter_factor = 1 - abs(2 * t - 1)  # Peak jitter in middle
            fatigue_factor = 1 + self.state.fatigue_level * 0.5

            if random.random() < jitter_factor * 0.5:
                point = self._add_micro_jitter(point[0], point[1], fatigue_factor)

            # Calculate timestamp with slight variance
            base_timestamp = t * duration
            timestamp_jitter = random.gauss(0, duration * 0.02)  # 2% timing variance
            timestamp = max(0, base_timestamp + timestamp_jitter)

            points.append((point[0], point[1], timestamp))

        # Sort by timestamp to ensure proper order after jitter
        points.sort(key=lambda p: p[2])

        return points

    def move_to(self, x: float, y: float, click: bool = False) -> bool:
        """Move mouse to target position with human-like behavior

        Args:
            x: Target x coordinate
            y: Target y coordinate
            click: Whether to click after reaching target

        Returns:
            True if movement completed successfully
        """
        if not PYAUTOGUI_AVAILABLE:
            logger.debug("pyautogui not available, skipping mouse movement")
            return False

        try:
            current_x, current_y = pyautogui.position()

            # Calculate distance
            distance = math.sqrt((x - current_x)**2 + (y - current_y)**2)

            if distance < 5:
                # Already at target
                if click:
                    self.human_click()
                return True

            # Update fatigue
            self._update_fatigue(distance)

            # Calculate duration
            duration = self._calculate_duration(distance)

            # Handle overshoot for long movements
            overshoot_end = None
            if (distance > 100 and
                random.random() < self._params['overshoot_probability']):
                # Overshoot by 5-15% of remaining distance
                overshoot_factor = random.uniform(1.05, 1.15)
                overshoot_x = current_x + (x - current_x) * overshoot_factor
                overshoot_y = current_y + (y - current_y) * overshoot_factor
                overshoot_end = (overshoot_x, overshoot_y)

            # Generate path
            target = overshoot_end if overshoot_end else (x, y)
            path_points = self._generate_path_points(
                (current_x, current_y), target, duration
            )

            # Execute movement
            start_time = time.time()
            last_x, last_y = current_x, current_y

            for px, py, point_time in path_points:
                # Wait for correct timing
                elapsed = time.time() - start_time
                if point_time > elapsed:
                    time.sleep(point_time - elapsed)

                # Move to point
                try:
                    pyautogui.moveTo(int(px), int(py), _pause=False)
                except pyautogui.FailSafeException:
                    logger.debug("Mouse moved to corner, resetting...")
                    return False

                # Track velocity for momentum
                self.state.velocity = (px - last_x, py - last_y)
                last_x, last_y = px, py

                # Occasional micro-pause
                if random.random() < self._params['pause_probability'] * 0.3:
                    pause = random.uniform(0.01, 0.05)
                    time.sleep(pause)

            # Correct overshoot if we did one
            if overshoot_end:
                time.sleep(random.uniform(0.05, 0.15))
                correction_path = self._generate_path_points(
                    overshoot_end, (x, y),
                    duration * 0.3  # Correction is faster
                )
                for px, py, _ in correction_path:
                    pyautogui.moveTo(int(px), int(py), _pause=False)
                    time.sleep(0.01)

            # Final position adjustment (humans often make small corrections)
            if random.random() < 0.2:
                time.sleep(random.uniform(0.05, 0.15))
                final_adjust_x = x + random.gauss(0, 1)
                final_adjust_y = y + random.gauss(0, 1)
                pyautogui.moveTo(int(final_adjust_x), int(final_adjust_y), _pause=False)

            # Update state
            self.state.last_move_time = time.time()
            self.state.total_distance_moved += distance

            # Optional pause before action
            if random.random() < self._params['pause_probability']:
                pause_time = random.uniform(*self._params['pause_duration'])
                time.sleep(pause_time * config.behavior.wait_factor)

            if click:
                self.human_click()

            return True

        except Exception as e:
            logger.debug(f"Mouse movement error: {e}")
            return False

    def human_click(self, button: str = 'left', double: bool = False):
        """Perform a human-like mouse click

        Real clicks have:
        - Variable hold duration (50-150ms typically)
        - Small movement during click sometimes
        - Occasional double-click mistakes
        """
        if not PYAUTOGUI_AVAILABLE:
            return

        try:
            # Pre-click micro-movement (settling hand)
            if random.random() < 0.3:
                current_x, current_y = pyautogui.position()
                settle_x = current_x + random.gauss(0, 1)
                settle_y = current_y + random.gauss(0, 1)
                pyautogui.moveTo(int(settle_x), int(settle_y), _pause=False)
                time.sleep(random.uniform(0.02, 0.08))

            # Variable click duration based on realistic distribution
            # Most clicks are quick, some are held slightly longer
            click_type = random.random()
            if click_type < 0.6:
                # Normal click
                hold_duration = random.gauss(0.085, 0.02)
            elif click_type < 0.85:
                # Quick click
                hold_duration = random.uniform(0.04, 0.07)
            elif click_type < 0.95:
                # Slightly longer hold
                hold_duration = random.uniform(0.12, 0.2)
            else:
                # Accidental long hold
                hold_duration = random.uniform(0.2, 0.35)

            hold_duration = max(0.03, hold_duration)  # Minimum hold time

            if double:
                # Double click with realistic inter-click delay
                # First click
                pyautogui.mouseDown(button=button, _pause=False)
                time.sleep(hold_duration)
                pyautogui.mouseUp(button=button, _pause=False)

                # Inter-click delay (typically 50-150ms for double-clicks)
                time.sleep(random.gauss(0.08, 0.025))

                # Second click (often slightly faster)
                pyautogui.mouseDown(button=button, _pause=False)
                time.sleep(hold_duration * random.uniform(0.7, 1.0))
                pyautogui.mouseUp(button=button, _pause=False)
            else:
                # Single click with possible micro-movement during
                pyautogui.mouseDown(button=button, _pause=False)

                # Sometimes move slightly while clicking (natural)
                if random.random() < 0.15:
                    current_x, current_y = pyautogui.position()
                    mid_x = current_x + random.gauss(0, 0.5)
                    mid_y = current_y + random.gauss(0, 0.5)
                    pyautogui.moveTo(int(mid_x), int(mid_y), _pause=False)

                time.sleep(hold_duration)
                pyautogui.mouseUp(button=button, _pause=False)

            # Post-click drift (hand relaxation)
            if random.random() < 0.25:
                time.sleep(random.uniform(0.02, 0.08))
                current_x, current_y = pyautogui.position()
                drift_x = current_x + random.gauss(0, 2)
                drift_y = current_y + random.gauss(0, 2)
                pyautogui.moveTo(int(drift_x), int(drift_y), _pause=False)

            self.state.click_count += 1

        except Exception as e:
            logger.debug(f"Click error: {e}")

    def random_movement(self, bounds: Tuple[int, int, int, int] = None):
        """Make a random movement within screen or given bounds

        Args:
            bounds: Optional (x1, y1, x2, y2) to constrain movement area
        """
        if not PYAUTOGUI_AVAILABLE:
            return

        try:
            if bounds:
                target_x = random.randint(bounds[0], bounds[2])
                target_y = random.randint(bounds[1], bounds[3])
            else:
                screen_width, screen_height = pyautogui.size()
                # Stay away from edges
                margin = 100
                target_x = random.randint(margin, screen_width - margin)
                target_y = random.randint(margin, screen_height - margin)

            self.move_to(target_x, target_y)

        except Exception as e:
            logger.debug(f"Random movement error: {e}")

    def idle_movement(self, duration: float = 5.0):
        """Simulate idle mouse behavior over a period of time

        When users read or think, they still make small movements
        """
        if not PYAUTOGUI_AVAILABLE:
            time.sleep(duration)
            return

        try:
            start = time.time()
            current_x, current_y = pyautogui.position()

            # Idle movement patterns
            idle_patterns = ['drift', 'circle', 'jitter', 'still']
            current_pattern = random.choice(idle_patterns)
            pattern_duration = random.uniform(1.0, 3.0)
            pattern_start = time.time()

            while time.time() - start < duration:
                # Switch patterns occasionally
                if time.time() - pattern_start > pattern_duration:
                    current_pattern = random.choice(idle_patterns)
                    pattern_duration = random.uniform(1.0, 3.0)
                    pattern_start = time.time()

                if current_pattern == 'drift':
                    # Slow drift in a direction
                    drift_x = current_x + random.gauss(0, 8)
                    drift_y = current_y + random.gauss(0, 8)
                    pyautogui.moveTo(
                        int(drift_x), int(drift_y),
                        duration=random.uniform(0.2, 0.5),
                        _pause=False
                    )
                    current_x, current_y = drift_x, drift_y
                    time.sleep(random.uniform(0.3, 1.0))

                elif current_pattern == 'circle':
                    # Small circular movement
                    angle = random.uniform(0, 2 * math.pi)
                    radius = random.uniform(5, 15)
                    circle_x = current_x + math.cos(angle) * radius
                    circle_y = current_y + math.sin(angle) * radius
                    pyautogui.moveTo(
                        int(circle_x), int(circle_y),
                        duration=random.uniform(0.1, 0.3),
                        _pause=False
                    )
                    time.sleep(random.uniform(0.2, 0.6))

                elif current_pattern == 'jitter':
                    # Quick small jitters
                    for _ in range(random.randint(2, 5)):
                        jitter_x = current_x + random.gauss(0, 3)
                        jitter_y = current_y + random.gauss(0, 3)
                        pyautogui.moveTo(int(jitter_x), int(jitter_y), _pause=False)
                        time.sleep(random.uniform(0.02, 0.08))
                    time.sleep(random.uniform(0.3, 0.8))

                else:  # still
                    # No movement, just wait
                    time.sleep(random.uniform(0.5, 2.0))

        except Exception as e:
            logger.debug(f"Idle movement error: {e}")


class HumanScroll:
    """Simulate realistic human scrolling behavior"""

    def __init__(self):
        self.last_scroll_time = 0
        self.total_scrolled = 0
        self.scroll_momentum = 0

    def scroll(self, direction: str = 'down', intensity: str = 'normal'):
        """Perform human-like scroll

        Args:
            direction: 'up' or 'down'
            intensity: 'light', 'normal', or 'heavy'
        """
        if not PYAUTOGUI_AVAILABLE:
            return

        intensities = {
            'light': (1, 3),
            'normal': (3, 7),
            'heavy': (7, 15),
        }

        scroll_range = intensities.get(intensity, intensities['normal'])
        scroll_amount = random.randint(*scroll_range)

        if direction == 'up':
            scroll_amount = -scroll_amount

        try:
            # Humans don't scroll at perfectly constant speed
            # Break into smaller scrolls with micro-pauses
            remaining = abs(scroll_amount)
            sign = 1 if scroll_amount > 0 else -1

            # Simulate scroll inertia
            chunks = []
            while remaining > 0:
                # Start fast, slow down (like flicking a scroll wheel)
                progress = 1 - (remaining / abs(scroll_amount))
                chunk_size = max(1, int(random.uniform(1, 3) * (1 - progress * 0.5)))
                chunk = min(remaining, chunk_size)
                chunks.append(chunk)
                remaining -= chunk

            for i, chunk in enumerate(chunks):
                pyautogui.scroll(chunk * sign)

                if i < len(chunks) - 1:
                    # Variable delay between scroll chunks
                    # Faster at start, slower at end
                    progress = i / len(chunks)
                    base_delay = 0.02 + progress * 0.06
                    time.sleep(random.uniform(base_delay * 0.5, base_delay * 1.5))

            self.last_scroll_time = time.time()
            self.total_scrolled += abs(scroll_amount)

        except Exception as e:
            logger.debug(f"Scroll error: {e}")

    def momentum_scroll(self, direction: str = 'down', strength: float = 1.0):
        """Perform a momentum-based scroll (like trackpad scrolling)

        Args:
            direction: 'up' or 'down'
            strength: How strong the initial "flick" is (0.5-2.0)
        """
        if not PYAUTOGUI_AVAILABLE:
            return

        try:
            initial_speed = random.uniform(8, 15) * strength
            friction = random.uniform(0.85, 0.92)

            sign = -1 if direction == 'up' else 1
            velocity = initial_speed * sign

            while abs(velocity) > 0.5:
                scroll_amount = int(velocity)
                if scroll_amount != 0:
                    pyautogui.scroll(scroll_amount)

                velocity *= friction

                # Variable timing
                time.sleep(random.uniform(0.015, 0.035))

        except Exception as e:
            logger.debug(f"Momentum scroll error: {e}")

    def smooth_scroll_to_element(self, driver, element):
        """Scroll element into view with human-like behavior"""
        try:
            # Get element position
            location = element.location
            size = element.size

            # Calculate scroll target
            viewport_height = driver.execute_script("return window.innerHeight")
            current_scroll = driver.execute_script("return window.pageYOffset")

            element_center_y = location['y'] + size['height'] / 2

            # Don't always center - sometimes scroll just enough
            if random.random() < 0.3:
                # Scroll so element is in upper third
                target_scroll = element_center_y - viewport_height * 0.3
            elif random.random() < 0.5:
                # Scroll so element is in lower third
                target_scroll = element_center_y - viewport_height * 0.7
            else:
                # Center it
                target_scroll = element_center_y - viewport_height / 2

            # Scroll in steps
            scroll_distance = target_scroll - current_scroll

            if abs(scroll_distance) < 50:
                return  # Already visible

            steps = max(5, int(abs(scroll_distance) / 100))

            for i in range(steps):
                progress = (i + 1) / steps
                # Ease out with slight overshoot possibility
                if random.random() < 0.1 and i == steps - 1:
                    eased_progress = 1.05  # Slight overshoot
                else:
                    eased_progress = 1 - (1 - progress) ** 2

                intermediate_scroll = current_scroll + scroll_distance * eased_progress
                driver.execute_script(f"window.scrollTo(0, {intermediate_scroll})")

                time.sleep(random.uniform(0.03, 0.08))

            # Correct overshoot
            if random.random() < 0.3:
                time.sleep(random.uniform(0.1, 0.3))
                adjustment = random.randint(-30, 30)
                driver.execute_script(f"window.scrollBy(0, {adjustment})")

        except Exception as e:
            logger.debug(f"Smooth scroll error: {e}")


class HumanTiming:
    """Manage realistic timing and delays"""

    @staticmethod
    def reading_delay(text_length: int = 100, complexity: str = 'normal') -> float:
        """Calculate realistic reading time based on text length and complexity

        Average reading speed is ~250 words per minute for normal text
        Technical content is slower (~150 WPM)
        """
        # Assume average word is 5 characters
        estimated_words = text_length / 5

        # Words per minute based on complexity
        wpm = {
            'simple': 300,
            'normal': 250,
            'technical': 150,
            'code': 100,
        }.get(complexity, 250)

        # Words per second
        wps = wpm / 60
        base_time = estimated_words / wps

        # Add variance (some people read faster/slower)
        variance = random.uniform(0.7, 1.5)

        # Add occasional re-reading
        if random.random() < 0.1:
            variance *= random.uniform(1.3, 1.8)

        return max(0.5, base_time * variance)

    @staticmethod
    def think_delay(task_complexity: str = 'normal') -> float:
        """Random thinking/processing delay based on task complexity"""
        delays = {
            'instant': (0.1, 0.3),
            'simple': (0.2, 0.8),
            'normal': (0.5, 2.0),
            'complex': (1.5, 4.0),
            'difficult': (3.0, 8.0),
        }

        min_delay, max_delay = delays.get(task_complexity, delays['normal'])

        # Use log-normal for more realistic distribution
        mean = (min_delay + max_delay) / 2
        delay = random.lognormvariate(math.log(mean), 0.4)

        return max(min_delay, min(delay, max_delay * 1.5))

    @staticmethod
    def reaction_delay() -> float:
        """Human reaction time delay (200-400ms typically)

        Based on actual human reaction time studies
        """
        # Normal distribution around 275ms
        delay = random.gauss(0.275, 0.05)
        return max(0.15, min(delay, 0.5))

    @staticmethod
    def page_engagement_time(page_type: str = 'content') -> float:
        """Calculate realistic time spent on a page type

        Args:
            page_type: 'landing', 'content', 'product', 'checkout', 'ad'
        """
        times = {
            'landing': (5, 15),
            'content': (15, 60),
            'product': (20, 90),
            'checkout': (30, 120),
            'ad': (10, 45),
            'search_results': (5, 20),
            'article': (30, 180),
        }

        time_range = times.get(page_type, times['content'])

        # Log-normal distribution for more realistic variance
        mean = (time_range[0] + time_range[1]) / 2
        base_time = random.lognormvariate(math.log(mean), 0.5)

        # Occasional very short or very long engagement
        if random.random() < 0.05:
            base_time *= random.choice([0.3, 2.5])

        return max(time_range[0] * 0.5, min(base_time, time_range[1] * 1.5))

    @staticmethod
    def typing_delay(char: str, prev_char: str = None) -> float:
        """Calculate delay between keystrokes for realistic typing

        Based on actual typing patterns - some key combinations are faster
        """
        base_delay = random.gauss(0.12, 0.03)

        # Same hand consecutive keys are slightly faster
        left_hand = 'qwertasdfgzxcvb'
        right_hand = 'yuiophjklnm'

        if prev_char:
            same_hand = ((char.lower() in left_hand and prev_char.lower() in left_hand) or
                        (char.lower() in right_hand and prev_char.lower() in right_hand))
            if same_hand:
                base_delay *= 0.85

        # Shift key adds delay
        if char.isupper() or char in '!@#$%^&*()_+{}|:"<>?':
            base_delay += random.uniform(0.03, 0.08)

        # Space is usually fast
        if char == ' ':
            base_delay *= 0.8

        # Occasional pause (thinking while typing)
        if random.random() < 0.02:
            base_delay += random.uniform(0.3, 1.0)

        # Occasional burst of speed
        if random.random() < 0.1:
            base_delay *= 0.6

        return max(0.03, base_delay)


class HumanInteraction:
    """High-level human interaction patterns"""

    def __init__(self, driver=None):
        self.driver = driver
        self.mouse = HumanMouse()
        self.scroll = HumanScroll()
        self.timing = HumanTiming()
        self.session_start = time.time()
        self.interactions_count = 0

    def _get_session_fatigue(self) -> float:
        """Calculate fatigue factor based on session length"""
        session_duration = time.time() - self.session_start
        # Fatigue increases over 30+ minutes
        fatigue = min(1.0, session_duration / 3600)  # Max at 1 hour
        return 1 + fatigue * 0.2  # Up to 20% slower

    def _get_element_screen_position(self, element) -> Tuple[int, int]:
        """Get element position in screen coordinates (not DOM coordinates)
        
        This converts DOM element location to actual screen coordinates
        accounting for browser chrome, scroll position, etc.
        """
        if not self.driver:
            return (0, 0)
            
        try:
            # Get element location relative to viewport
            location = element.location
            size = element.size
            
            # Get scroll position
            scroll_x = self.driver.execute_script("return window.pageXOffset || document.documentElement.scrollLeft")
            scroll_y = self.driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop")
            
            # Get browser window position (outer position)
            # This accounts for browser chrome (address bar, tabs, etc.)
            try:
                window_x = self.driver.execute_script("return window.screenX || window.screenLeft || 0")
                window_y = self.driver.execute_script("return window.screenY || window.screenTop || 0")
            except:
                window_x, window_y = 0, 0
            
            # Get the difference between outer and inner window (browser chrome height)
            try:
                outer_height = self.driver.execute_script("return window.outerHeight")
                inner_height = self.driver.execute_script("return window.innerHeight")
                chrome_height = outer_height - inner_height
                
                outer_width = self.driver.execute_script("return window.outerWidth")
                inner_width = self.driver.execute_script("return window.innerWidth")
                chrome_width = (outer_width - inner_width) // 2  # Assume symmetric
            except:
                chrome_height = 100  # Approximate browser chrome height
                chrome_width = 0
            
            # Calculate element center in viewport coordinates
            element_viewport_x = location['x'] - scroll_x + size['width'] / 2
            element_viewport_y = location['y'] - scroll_y + size['height'] / 2
            
            # Convert to screen coordinates
            screen_x = window_x + chrome_width + element_viewport_x
            screen_y = window_y + chrome_height + element_viewport_y
            
            # Add slight randomness to not always click dead center
            offset_x = random.gauss(0, size['width'] * 0.1)
            offset_y = random.gauss(0, size['height'] * 0.1)
            
            # Clamp offsets to stay within element
            offset_x = max(-size['width'] * 0.35, min(offset_x, size['width'] * 0.35))
            offset_y = max(-size['height'] * 0.35, min(offset_y, size['height'] * 0.35))
            
            return (int(screen_x + offset_x), int(screen_y + offset_y))
            
        except Exception as e:
            logger.debug(f"Error getting screen position: {e}")
            # Fallback to basic calculation
            location = element.location
            size = element.size
            return (int(location['x'] + size['width'] / 2), int(location['y'] + size['height'] / 2))

    def human_scroll(self, amount: int = None, direction: str = None, intensity: str = 'normal'):
        """Convenience method for human-like scrolling.

        This method delegates to the internal HumanScroll instance and provides
        backward compatibility for code that calls human_scroll() directly.

        Args:
            amount: Scroll amount (positive = down, negative = up). If provided,
                   determines direction and uses momentum_scroll for larger amounts.
            direction: 'up' or 'down' (used if amount not provided)
            intensity: 'light', 'normal', or 'heavy'
        """
        if amount is not None:
            # Determine direction from amount
            if amount > 0:
                scroll_direction = 'down'
            elif amount < 0:
                scroll_direction = 'up'
            else:
                return  # No scroll needed

            abs_amount = abs(amount)

            # Use momentum scroll for larger amounts, regular for smaller
            if abs_amount > 300:
                # Convert pixel amount to strength (rough approximation)
                strength = min(2.0, abs_amount / 500)
                self.scroll.momentum_scroll(scroll_direction, strength)
            else:
                # Map amount to intensity
                if abs_amount < 100:
                    scroll_intensity = 'light'
                elif abs_amount < 250:
                    scroll_intensity = 'normal'
                else:
                    scroll_intensity = 'heavy'
                self.scroll.scroll(scroll_direction, scroll_intensity)
        elif direction:
            self.scroll.scroll(direction, intensity)
        else:
            # Default: scroll down with normal intensity
            self.scroll.scroll('down', intensity)

    def human_scroll_to_element(self, element):
        """Scroll to bring element into view with human-like behavior
        
        Args:
            element: Selenium WebElement to scroll to
        """
        self.scroll.smooth_scroll_to_element(self.driver, element)

    def move_to_element_human(self, element):
        """Move mouse to element using screen coordinates with human-like bezier movement
        
        Args:
            element: Selenium WebElement to move to
        """
        try:
            # First ensure element is in view
            self.scroll.smooth_scroll_to_element(self.driver, element)
            time.sleep(random.uniform(0.1, 0.3))
            
            # Get screen coordinates
            screen_x, screen_y = self._get_element_screen_position(element)
            
            # Move with human-like behavior
            self.mouse.move_to(screen_x, screen_y, click=False)
            
        except Exception as e:
            logger.debug(f"Move to element error: {e}")

    def human_click(self, element):
        """Click element using screen coordinates with human-like behavior
        
        This uses pyautogui to move to actual screen coordinates and click,
        providing more realistic mouse movement than Selenium's click().
        
        Args:
            element: Selenium WebElement to click
        """
        try:
            # Ensure element is scrolled into view
            self.scroll.smooth_scroll_to_element(self.driver, element)
            time.sleep(random.uniform(0.1, 0.3))
            
            # Get screen coordinates
            screen_x, screen_y = self._get_element_screen_position(element)
            
            logger.debug(f"Human click at screen coordinates: ({screen_x}, {screen_y})")
            
            # Move to element and click with human-like behavior
            self.mouse.move_to(screen_x, screen_y, click=True)
            
        except Exception as e:
            logger.debug(f"Human click error: {e}")
            # Fallback to Selenium click
            try:
                element.click()
            except:
                pass

    def bezier_mouse_move(self, target_x: int, target_y: int):
        """Move mouse to target position using bezier curves
        
        Args:
            target_x: Target X screen coordinate
            target_y: Target Y screen coordinate
        """
        self.mouse.move_to(target_x, target_y, click=False)

    def add_micro_movements(self, num_movements: int = 3):
        """Add small random micro-movements at current position
        
        Args:
            num_movements: Number of small movements to make
        """
        if not PYAUTOGUI_AVAILABLE:
            return
            
        try:
            for _ in range(num_movements):
                current_x, current_y = pyautogui.position()
                # Small random offset
                new_x = current_x + random.gauss(0, 3)
                new_y = current_y + random.gauss(0, 3)
                pyautogui.moveTo(int(new_x), int(new_y), duration=random.uniform(0.02, 0.08), _pause=False)
                time.sleep(random.uniform(0.02, 0.1))
        except Exception as e:
            logger.debug(f"Micro movement error: {e}")

    def browse_page(self, duration: float = None):
        """Simulate realistic page browsing behavior

        Combines scrolling, mouse movements, and pauses
        """
        if duration is None:
            duration = self.timing.page_engagement_time('content')

        start_time = time.time()
        fatigue = self._get_session_fatigue()

        logger.debug(f"Browsing page for {duration:.1f} seconds...")

        # Track scroll position to avoid scrolling too far
        total_scrolled = 0
        max_scroll = random.randint(3, 10)  # Max scroll actions
        scroll_count = 0

        while time.time() - start_time < duration:
            # Adjust probabilities based on scroll position
            can_scroll = scroll_count < max_scroll

            weights = [
                0.35 if can_scroll else 0.0,  # scroll
                0.25,  # mouse_move
                0.25,  # pause
                0.15,  # idle
            ]

            # Normalize weights
            total_weight = sum(weights)
            weights = [w / total_weight for w in weights]

            action = random.choices(
                ['scroll', 'mouse_move', 'pause', 'idle'],
                weights=weights
            )[0]

            if action == 'scroll':
                # Prefer scrolling down, but occasionally up
                direction = 'up' if (random.random() < 0.2 and scroll_count > 2) else 'down'
                intensity = random.choice(['light', 'normal', 'normal'])

                # Sometimes use momentum scroll
                if random.random() < 0.3:
                    self.scroll.momentum_scroll(direction, random.uniform(0.7, 1.3))
                else:
                    self.scroll.scroll(direction, intensity)

                scroll_count += 1
                time.sleep(random.uniform(0.5, 2.0) * config.behavior.wait_factor * fatigue)

            elif action == 'mouse_move':
                self.mouse.random_movement()
                time.sleep(random.uniform(0.3, 1.0) * config.behavior.wait_factor * fatigue)

            elif action == 'pause':
                pause_time = self.timing.think_delay()
                time.sleep(pause_time * config.behavior.wait_factor * fatigue)

            elif action == 'idle':
                idle_time = random.uniform(1.0, 3.0)
                self.mouse.idle_movement(idle_time * config.behavior.wait_factor * fatigue)

        self.interactions_count += 1

    def click_element(self, element, pre_hover: bool = True) -> bool:
        """Click an element with realistic human behavior

        Args:
            element: Selenium WebElement to click
            pre_hover: Whether to hover before clicking

        Returns:
            True if click was successful
        """
        try:
            # Scroll element into view smoothly
            self.scroll.smooth_scroll_to_element(self.driver, element)
            time.sleep(self.timing.reaction_delay() * config.behavior.wait_factor)

            # Get element screen coordinates
            screen_x, screen_y = self._get_element_screen_position(element)

            if pre_hover:
                # Sometimes approach from a random direction first
                if random.random() < 0.2:
                    approach_x = screen_x + random.uniform(-100, 100)
                    approach_y = screen_y + random.uniform(-50, 50)
                    self.mouse.move_to(approach_x, approach_y, click=False)
                    time.sleep(random.uniform(0.1, 0.3))

                # Move to element and pause (reading/considering)
                self.mouse.move_to(screen_x, screen_y, click=False)

                # Variable hover time based on element type
                hover_time = random.uniform(0.2, 0.8)
                if random.random() < 0.1:
                    # Occasionally hesitate longer
                    hover_time = random.uniform(0.8, 1.5)
                time.sleep(hover_time * config.behavior.wait_factor)

            # Click
            self.mouse.move_to(screen_x, screen_y, click=True)
            self.interactions_count += 1

            return True

        except Exception as e:
            logger.debug(f"Element click error: {e}")
            return False

    def hover_random_elements(self, elements: list, count: int = 3):
        """Hover over random elements to simulate browsing

        This makes behavior look more natural - users don't just
        click the first thing they see
        """
        if not elements or not PYAUTOGUI_AVAILABLE:
            return

        hover_count = min(count, len(elements))

        # Don't just pick random - sometimes scan in order
        if random.random() < 0.3:
            # Scan from top to bottom
            selected = elements[:hover_count]
        else:
            selected = random.sample(elements, hover_count)

        for element in selected:
            try:
                self.scroll.smooth_scroll_to_element(self.driver, element)

                screen_x, screen_y = self._get_element_screen_position(element)
                self.mouse.move_to(screen_x, screen_y)

                # Brief pause as if reading - variable based on element size
                size = element.size
                read_time = max(0.5, size['height'] / 100)  # More time for larger elements
                time.sleep(random.uniform(0.5, read_time * 2) * config.behavior.wait_factor)

            except Exception as e:
                logger.debug(f"Hover error: {e}")
                continue

    def distracted_browse(self, duration: float = 10.0):
        """Simulate distracted browsing (checking other things)

        Users often get distracted - move mouse to edges,
        pause for long periods, etc.
        """
        if not PYAUTOGUI_AVAILABLE:
            time.sleep(duration)
            return

        try:
            screen_width, screen_height = pyautogui.size()
            start = time.time()

            while time.time() - start < duration:
                distraction = random.choice([
                    'taskbar',
                    'edge',
                    'nothing',
                    'scroll_away'
                ])

                if distraction == 'taskbar':
                    # Move to bottom of screen (taskbar area)
                    self.mouse.move_to(
                        random.randint(100, screen_width - 100),
                        screen_height - random.randint(10, 40)
                    )
                    time.sleep(random.uniform(1, 3))

                elif distraction == 'edge':
                    # Move to screen edge
                    edge = random.choice(['left', 'right', 'top'])
                    if edge == 'left':
                        x, y = 5, random.randint(100, screen_height - 100)
                    elif edge == 'right':
                        x, y = screen_width - 5, random.randint(100, screen_height - 100)
                    else:
                        x, y = random.randint(100, screen_width - 100), 5
                    self.mouse.move_to(x, y)
                    time.sleep(random.uniform(0.5, 2))

                elif distraction == 'nothing':
                    # Just pause
                    time.sleep(random.uniform(2, 5))

                elif distraction == 'scroll_away' and self.driver:
                    # Scroll to a random position
                    self.scroll.momentum_scroll(
                        random.choice(['up', 'down']),
                        random.uniform(0.5, 1.5)
                    )
                    time.sleep(random.uniform(1, 3))

        except Exception as e:
            logger.debug(f"Distracted browse error: {e}")

    def random_page_engagement(self, min_time: float = 2.0, max_time: float = 4.0):
        """Simulate random page engagement for a variable duration.

        This method is called when you need a quick, realistic engagement
        pattern with scrolling, mouse movements, and pauses for a random
        duration within the specified bounds.

        Args:
            min_time: Minimum engagement duration in seconds
            max_time: Maximum engagement duration in seconds
        """
        # Calculate random duration using log-normal for realistic variance
        mean_time = (min_time + max_time) / 2
        duration = random.lognormvariate(math.log(mean_time), 0.3)
        duration = max(min_time, min(duration, max_time * 1.2))

        logger.debug(f"Random page engagement for {duration:.1f} seconds")

        start_time = time.time()
        fatigue = self._get_session_fatigue()

        while time.time() - start_time < duration:
            # Quick, varied actions
            action = random.choices(
                ['scroll', 'mouse_move', 'pause', 'idle'],
                weights=[0.3, 0.3, 0.25, 0.15]
            )[0]

            if action == 'scroll':
                direction = random.choice(['down', 'down', 'up'])  # Bias toward down
                if random.random() < 0.4:
                    self.scroll.momentum_scroll(direction, random.uniform(0.5, 1.0))
                else:
                    self.scroll.scroll(direction, random.choice(['light', 'normal']))
                time.sleep(random.uniform(0.3, 0.8) * fatigue)

            elif action == 'mouse_move':
                self.mouse.random_movement()
                time.sleep(random.uniform(0.2, 0.5) * fatigue)

            elif action == 'pause':
                time.sleep(random.uniform(0.3, 1.0) * fatigue)

            elif action == 'idle':
                self.mouse.idle_movement(random.uniform(0.5, 1.5) * fatigue)

        self.interactions_count += 1


# Global instances for easy access
human_mouse = HumanMouse()
human_scroll = HumanScroll()
human_timing = HumanTiming()


def get_human_interaction(driver=None) -> HumanInteraction:
    """Get a HumanInteraction instance"""
    return HumanInteraction(driver)


# Alias for backward compatibility with search_controller.py
HumanSimulation = HumanInteraction
