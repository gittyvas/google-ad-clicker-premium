#!/usr/bin/env python3
"""
Advanced Human Simulation Usage - Production Ready

Demonstrates production patterns for using the human simulation module
including error handling, retries, async operations, and real-world scenarios.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import (
    Any, Callable, Dict, List, Optional, 
    Tuple, TypeVar, Union, Iterator
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import simulation module
from human_simulation import (
    HumanSimulation,
    AsyncHumanSimulation,
    HumanMouse,
    HumanScroll,
    HumanTiming,
    HumanInteraction,
    SimulationConfig,
    MovementStyle,
    ScrollIntensity,
    TaskComplexity,
    PageType,
    get_config,
    set_config,
    config_override,
    create_simulation,
    human_mouse,
    human_scroll,
    human_timing,
    SimulationError,
    MouseMovementError,
    ScrollError,
    ElementInteractionError,
)

# Check for Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.common.exceptions import (
        TimeoutException, 
        NoSuchElementException,
        StaleElementReferenceException,
        WebDriverException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not installed. Web automation features disabled.")

T = TypeVar('T')


# ============================================================================
# Decorators and Utilities
# ============================================================================

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,)
) -> Callable:
    """Retry decorator with exponential backoff"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            
            raise last_exception
        return wrapper
    return decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,)
) -> Callable:
    """Async retry decorator with exponential backoff"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            
            raise last_exception
        return wrapper
    return decorator


@contextmanager
def simulation_session(
    driver: Optional[Any] = None,
    style: Optional[MovementStyle] = None,
    **config_kwargs
) -> Iterator[HumanSimulation]:
    """Context manager for simulation sessions with automatic cleanup"""
    sim = create_simulation(driver=driver, style=style, **config_kwargs)
    try:
        yield sim
    finally:
        stats = sim.get_stats()
        logger.info(f"Session stats: {stats}")
        sim.reset()


# ============================================================================
# Production Simulation Wrapper
# ============================================================================

@dataclass
class SimulationResult:
    """Result of a simulation action"""
    success: bool
    action: str
    duration: float
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ProductionSimulator:
    """Production-ready simulator with comprehensive error handling"""
    
    def __init__(
        self,
        driver: Optional[Any] = None,
        config: Optional[SimulationConfig] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.config = config or SimulationConfig()
        set_config(self.config)
        
        self.sim = HumanSimulation(driver=driver)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.action_history: List[SimulationResult] = []
        self._start_time = time.time()
    
    @property
    def driver(self) -> Optional[Any]:
        return self.sim.driver
    
    @driver.setter
    def driver(self, value: Any) -> None:
        self.sim.driver = value
    
    def _record_action(self, result: SimulationResult) -> None:
        """Record action result"""
        self.action_history.append(result)
        if len(self.action_history) > 1000:
            self.action_history = self.action_history[-500:]
    
    def _execute_with_retry(
        self,
        action_name: str,
        func: Callable[[], T],
        exceptions: Tuple[type, ...] = (SimulationError, Exception)
    ) -> SimulationResult:
        """Execute action with retry logic"""
        start = time.time()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                result = func()
                duration = time.time() - start
                sim_result = SimulationResult(
                    success=True,
                    action=action_name,
                    duration=duration,
                    data={'result': result, 'attempts': attempt + 1}
                )
                self._record_action(sim_result)
                return sim_result
                
            except exceptions as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    logger.warning(f"{action_name} failed (attempt {attempt + 1}): {e}")
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"{action_name} failed after {self.max_retries} attempts: {e}")
        
        duration = time.time() - start
        sim_result = SimulationResult(
            success=False,
            action=action_name,
            duration=duration,
            error=last_error
        )
        self._record_action(sim_result)
        return sim_result
    
    # Mouse actions
    def move_to(self, x: float, y: float, click: bool = False) -> SimulationResult:
        """Move mouse with retry"""
        return self._execute_with_retry(
            f"move_to({x}, {y}, click={click})",
            lambda: self.sim.move_to(x, y, click)
        )
    
    def click(self, button: str = 'left', double: bool = False) -> SimulationResult:
        """Click with retry"""
        return self._execute_with_retry(
            f"click(button={button}, double={double})",
            lambda: self.sim.click(button, double)
        )
    
    def double_click(self) -> SimulationResult:
        """Double click"""
        return self.click(double=True)
    
    def right_click(self) -> SimulationResult:
        """Right click"""
        return self.click(button='right')
    
    # Scroll actions
    def scroll_down(self, intensity: str = 'normal') -> SimulationResult:
        """Scroll down with retry"""
        return self._execute_with_retry(
            f"scroll_down(intensity={intensity})",
            lambda: self.sim.scroll_down(intensity)
        )
    
    def scroll_up(self, intensity: str = 'normal') -> SimulationResult:
        """Scroll up with retry"""
        return self._execute_with_retry(
            f"scroll_up(intensity={intensity})",
            lambda: self.sim.scroll_up(intensity)
        )
    
    def momentum_scroll(self, direction: str = 'down', strength: float = 1.0) -> SimulationResult:
        """Momentum scroll"""
        return self._execute_with_retry(
            f"momentum_scroll(direction={direction})",
            lambda: self.sim.momentum_scroll(direction, strength)
        )
    
    # Timing actions
    def wait(self, complexity: str = 'normal') -> SimulationResult:
        """Wait with thinking delay"""
        start = time.time()
        delay = self.sim.wait(complexity)
        return SimulationResult(
            success=True,
            action=f"wait(complexity={complexity})",
            duration=time.time() - start,
            data={'delay': delay}
        )
    
    def read(self, text_length: int = 100, complexity: str = 'normal') -> SimulationResult:
        """Simulate reading"""
        start = time.time()
        delay = self.sim.read(text_length, complexity)
        return SimulationResult(
            success=True,
            action=f"read(length={text_length})",
            duration=time.time() - start,
            data={'delay': delay}
        )
    
    # Browsing actions
    def browse_page(self, duration: Optional[float] = None) -> SimulationResult:
        """Browse page with realistic behavior"""
        return self._execute_with_retry(
            f"browse_page(duration={duration})",
            lambda: self.sim.browse_page(duration)
        )
    
    def idle(self, duration: float = 5.0) -> SimulationResult:
        """Idle behavior"""
        return self._execute_with_retry(
            f"idle(duration={duration})",
            lambda: self.sim.idle(duration)
        )
    
    def distracted(self, duration: float = 10.0) -> SimulationResult:
        """Distracted browsing"""
        return self._execute_with_retry(
            f"distracted(duration={duration})",
            lambda: self.sim.distracted(duration)
        )
    
    # Element interactions (requires Selenium)
    def click_element(self, element: Any, pre_hover: bool = True) -> SimulationResult:
        """Click element with retry"""
        if not SELENIUM_AVAILABLE:
            return SimulationResult(
                success=False,
                action="click_element",
                duration=0,
                error="Selenium not available"
            )
        return self._execute_with_retry(
            "click_element",
            lambda: self.sim.click_element(element, pre_hover),
            exceptions=(ElementInteractionError, Exception)
        )
    
    def scroll_to_element(self, element: Any) -> SimulationResult:
        """Scroll to element"""
        if not SELENIUM_AVAILABLE:
            return SimulationResult(
                success=False,
                action="scroll_to_element",
                duration=0,
                error="Selenium not available"
            )
        return self._execute_with_retry(
            "scroll_to_element",
            lambda: self.sim.scroll_to_element(element)
        )
    
    def hover_elements(self, elements: List[Any], count: int = 3) -> SimulationResult:
        """Hover over elements"""
        return self._execute_with_retry(
            f"hover_elements(count={count})",
            lambda: self.sim.hover_elements(elements, count)
        )
    
    # Stats and reporting
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats"""
        sim_stats = self.sim.get_stats()
        
        successful_actions = sum(1 for r in self.action_history if r.success)
        failed_actions = sum(1 for r in self.action_history if not r.success)
        total_duration = sum(r.duration for r in self.action_history)
        
        return {
            **sim_stats,
            'total_actions': len(self.action_history),
            'successful_actions': successful_actions,
            'failed_actions': failed_actions,
            'success_rate': successful_actions / max(1, len(self.action_history)),
            'total_action_duration': total_duration,
            'uptime': time.time() - self._start_time,
        }
    
    def get_action_history(self, limit: int = 100) -> List[SimulationResult]:
        """Get recent action history"""
        return self.action_history[-limit:]
    
    def reset(self) -> None:
        """Reset simulator state"""
        self.sim.reset()
        self.action_history.clear()
        self._start_time = time.time()


# ============================================================================
# Web Automation Helper (Selenium Integration)
# ============================================================================

if SELENIUM_AVAILABLE:
    class WebAutomator:
        """Production web automation with human simulation"""
        
        def __init__(
            self,
            headless: bool = False,
            user_agent: Optional[str] = None,
            proxy: Optional[str] = None,
            window_size: Tuple[int, int] = (1920, 1080),
            implicit_wait: float = 10.0,
            simulation_config: Optional[SimulationConfig] = None
        ):
            self.headless = headless
            self.user_agent = user_agent
            self.proxy = proxy
            self.window_size = window_size
            self.implicit_wait = implicit_wait
            
            self.driver: Optional[webdriver.Chrome] = None
            self.simulator: Optional[ProductionSimulator] = None
            self.simulation_config = simulation_config or SimulationConfig()
        
        def _create_driver(self) -> webdriver.Chrome:
            """Create configured Chrome driver"""
            options = ChromeOptions()
            
            if self.headless:
                options.add_argument('--headless=new')
            
            options.add_argument(f'--window-size={self.window_size[0]},{self.window_size[1]}')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')
            
            if self.user_agent:
                options.add_argument(f'--user-agent={self.user_agent}')
            
            if self.proxy:
                options.add_argument(f'--proxy-server={self.proxy}')
            
            # Anti-detection
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            driver = webdriver.Chrome(options=options)
            driver.implicitly_wait(self.implicit_wait)
            
            # Remove webdriver property
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })
            
            return driver
        
        def start(self) -> 'WebAutomator':
            """Start the automation session"""
            self.driver = self._create_driver()
            self.simulator = ProductionSimulator(
                driver=self.driver,
                config=self.simulation_config
            )
            logger.info("Web automation session started")
            return self
        
        def stop(self) -> None:
            """Stop the automation session"""
            if self.simulator:
                stats = self.simulator.get_stats()
                logger.info(f"Session stats: {stats}")
            
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.warning(f"Error closing driver: {e}")
            
            self.driver = None
            self.simulator = None
            logger.info("Web automation session stopped")
        
        def __enter__(self) -> 'WebAutomator':
            return self.start()
        
        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            self.stop()
        
        def navigate(self, url: str) -> SimulationResult:
            """Navigate to URL with human-like delay"""
            if not self.driver or not self.simulator:
                raise RuntimeError("Session not started")
            
            start = time.time()
            try:
                self.driver.get(url)
                # Simulate page load reaction
                self.simulator.wait('simple')
                return SimulationResult(
                    success=True,
                    action=f"navigate({url})",
                    duration=time.time() - start
                )
            except Exception as e:
                return SimulationResult(
                    success=False,
                    action=f"navigate({url})",
                    duration=time.time() - start,
                    error=str(e)
                )
        
        def find_element(
            self,
            by: str,
            value: str,
            timeout: float = 10.0
        ) -> Optional[Any]:
            """Find element with wait"""
            if not self.driver:
                raise RuntimeError("Session not started")
            
            try:
                wait = WebDriverWait(self.driver, timeout)
                element = wait.until(
                    EC.presence_of_element_located((by, value))
                )
                return element
            except TimeoutException:
                logger.warning(f"Element not found: {by}={value}")
                return None
        
        def find_elements(
            self,
            by: str,
            value: str,
            timeout: float = 10.0
        ) -> List[Any]:
            """Find multiple elements"""
            if not self.driver:
                raise RuntimeError("Session not started")
            
            try:
                wait = WebDriverWait(self.driver, timeout)
                wait.until(EC.presence_of_element_located((by, value)))
                return self.driver.find_elements(by, value)
            except TimeoutException:
                return []
        
        def click_by_selector(
            self,
            selector: str,
            by: str = By.CSS_SELECTOR,
            pre_hover: bool = True
        ) -> SimulationResult:
            """Click element by selector"""
            if not self.simulator:
                raise RuntimeError("Session not started")
            
            element = self.find_element(by, selector)
            if not element:
                return SimulationResult(
                    success=False,
                    action=f"click_by_selector({selector})",
                    duration=0,
                    error="Element not found"
                )
            
            return self.simulator.click_element(element, pre_hover)
        
        def type_text(
            self,
            element: Any,
            text: str,
            clear_first: bool = True
        ) -> SimulationResult:
            """Type text with human-like timing"""
            if not self.simulator:
                raise RuntimeError("Session not started")
            
            start = time.time()
            try:
                # Click element first
                self.simulator.click_element(element, pre_hover=True)
                
                if clear_first:
                    element.clear()
                    self.simulator.wait('instant')
                
                # Type with realistic delays
                prev_char = None
                for char in text:
                    delay = human_timing.typing_delay(char, prev_char)
                    time.sleep(delay)
                    element.send_keys(char)
                    prev_char = char
                
                return SimulationResult(
                    success=True,
                    action=f"type_text(length={len(text)})",
                    duration=time.time() - start
                )
            except Exception as e:
                return SimulationResult(
                    success=False,
                    action="type_text",
                    duration=time.time() - start,
                    error=str(e)
                )
        
        def browse_and_interact(
            self,
            duration: float = 30.0,
            click_probability: float = 0.3,
            scroll_probability: float = 0.5
        ) -> SimulationResult:
            """Browse page with random interactions"""
            if not self.driver or not self.simulator:
                raise RuntimeError("Session not started")
            
            start = time.time()
            actions_taken = 0
            
            try:
                while time.time() - start < duration:
                    roll = random.random()
                    
                    if roll < click_probability:
                        # Try to click a random link
                        links = self.find_elements(By.TAG_NAME, "a", timeout=2)
                        if links:
                            import random
                            link = random.choice(links[:10])
                            try:
                                self.simulator.click_element(link, pre_hover=True)
                                actions_taken += 1
                            except Exception:
                                pass
                    
                    elif roll < click_probability + scroll_probability:
                        # Scroll
                        direction = 'down' if random.random() > 0.3 else 'up'
                        self.simulator.momentum_scroll(direction)
                        actions_taken += 1
                    
                    else:
                        # Idle
                        self.simulator.idle(random.uniform(1, 3))
                    
                    self.simulator.wait('simple')
                
                return SimulationResult(
                    success=True,
                    action="browse_and_interact",
                    duration=time.time() - start,
                    data={'actions_taken': actions_taken}
                )
            except Exception as e:
                return SimulationResult(
                    success=False,
                    action="browse_and_interact",
                    duration=time.time() - start,
                    error=str(e)
                )
        
        def screenshot(self, path: str) -> bool:
            """Take screenshot"""
            if not self.driver:
                return False
            try:
                self.driver.save_screenshot(path)
                return True
            except Exception as e:
                logger.error(f"Screenshot failed: {e}")
                return False


# ============================================================================
# Example Workflows
# ============================================================================

def example_basic_usage():
    """Basic usage example"""
    print("\n=== Basic Usage Example ===\n")
    
    # Create simulation with custom config
    config = SimulationConfig(
        wait_factor=1.0,
        speed_factor=1.0,
        enable_jitter=True,
        enable_fatigue=True,
        log_movements=True
    )
    
    with simulation_session(config=config) as sim:
        # Set a specific style
        sim.style = MovementStyle.NORMAL
        print(f"Using style: {sim.style.value}")
        
        # Move mouse
        result = sim.move_to(500, 300)
        print(f"Moved to (500, 300): {result}")
        
        # Click
        sim.click()
        print("Clicked")
        
        # Scroll
        sim.scroll_down('normal')
        print("Scrolled down")
        
        # Wait like thinking
        delay = sim.wait('complex')
        print(f"Waited {delay:.2f}s")
        
        # Simulate reading
        delay = sim.read(text_length=500, complexity='normal')
        print(f"Read for {delay:.2f}s")
        
        # Get stats
        stats = sim.get_stats()
        print(f"\nSession stats: {stats}")


def example_production_usage():
    """Production usage with retries and error handling"""
    print("\n=== Production Usage Example ===\n")
    
    # Create production simulator
    simulator = ProductionSimulator(
        config=SimulationConfig(
            wait_factor=0.8,
            speed_factor=1.2,
            debug_mode=True
        ),
        max_retries=3,
        retry_delay=0.5
    )
    
    # Execute actions with automatic retry
    result = simulator.move_to(600, 400, click=False)
    print(f"Move result: success={result.success}, duration={result.duration:.3f}s")
    
    result = simulator.scroll_down('heavy')
    print(f"Scroll result: success={result.success}")
    
    result = simulator.wait('complex')
    print(f"Wait result: delay={result.data.get('delay', 0):.2f}s")
    
    result = simulator.browse_page(duration=5.0)
    print(f"Browse result: success={result.success}")
    
    # Get comprehensive stats
    stats = simulator.get_stats()
    print(f"\nFinal stats:")
    print(f"  Total actions: {stats['total_actions']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")
    print(f"  Total distance: {stats['total_distance']:.0f}px")
    print(f"  Click count: {stats['click_count']}")
    
    simulator.reset()


async def example_async_usage():
    """Async usage example"""
    print("\n=== Async Usage Example ===\n")
    
    sim = HumanSimulation()
    async_sim = AsyncHumanSimulation(sim)
    
    # Execute async operations
    result = await async_sim.move_to(400, 300)
    print(f"Async move: {result}")
    
    await async_sim.click()
    print("Async click completed")
    
    delay = await async_sim.wait('normal')
    print(f"Async wait: {delay:.2f}s")
    
    await async_sim.scroll_down('normal')
    print("Async scroll completed")


def example_web_automation():
    """Web automation example (requires Selenium)"""
    if not SELENIUM_AVAILABLE:
        print("\n=== Web Automation Example (SKIPPED - Selenium not installed) ===\n")
        return
    
    print("\n=== Web Automation Example ===\n")
    
    # Use context manager for automatic cleanup
    with WebAutomator(
        headless=True,  # Set to False to see the browser
        window_size=(1280, 720),
        simulation_config=SimulationConfig(wait_factor=0.5)
    ) as automator:
        
        # Navigate to a page
        result = automator.navigate("https://example.com")
        print(f"Navigation: {result.success}")
        
        # Browse the page
        result = automator.simulator.browse_page(duration=5.0)
        print(f"Browsing: {result.success}")
        
        # Find and click a link
        result = automator.click_by_selector("a", pre_hover=True)
        print(f"Click link: {result.success}")
        
        # Take screenshot
        automator.screenshot("screenshot.png")
        print("Screenshot saved")
        
        # Get final stats
        stats = automator.simulator.get_stats()
        print(f"\nAutomation stats: {stats}")


def example_style_comparison():
    """Compare different movement styles"""
    print("\n=== Style Comparison Example ===\n")
    
    styles = [
        MovementStyle.RELAXED,
        MovementStyle.NORMAL,
        MovementStyle.IMPATIENT,
        MovementStyle.CAUTIOUS,
        MovementStyle.ERRATIC,
    ]
    
    for style in styles:
        sim = HumanSimulation(style=style)
        
        start = time.time()
        sim.move_to(500, 300)
        duration = time.time() - start
        
        print(f"{style.value:12} style: move duration = {duration:.3f}s")


def example_config_override():
    """Demonstrate config override"""
    print("\n=== Config Override Example ===\n")
    
    # Set base config
    set_config(SimulationConfig(wait_factor=1.0, speed_factor=1.0))
    print(f"Base config: wait_factor={get_config().wait_factor}")
    
    # Temporarily override
    with config_override(wait_factor=0.5, speed_factor=2.0):
        print(f"Overridden: wait_factor={get_config().wait_factor}")
        
        sim = HumanSimulation()
        sim.wait('simple')  # Will be faster due to override
    
    print(f"Restored: wait_factor={get_config().wait_factor}")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main entry point with CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Human Simulation Production Examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python usage.py --basic          Run basic usage example
  python usage.py --production     Run production usage example
  python usage.py --async          Run async usage example
  python usage.py --web            Run web automation example
  python usage.py --styles         Compare movement styles
  python usage.py --all            Run all examples
        """
    )
    
    parser.add_argument('--basic', action='store_true', help='Run basic usage example')
    parser.add_argument('--production', action='store_true', help='Run production usage example')
    parser.add_argument('--async', dest='run_async', action='store_true', help='Run async example')
    parser.add_argument('--web', action='store_true', help='Run web automation example')
    parser.add_argument('--styles', action='store_true', help='Compare movement styles')
    parser.add_argument('--config', action='store_true', help='Config override example')
    parser.add_argument('--all', action='store_true', help='Run all examples')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # If no args, show help
    if not any([args.basic, args.production, args.run_async, 
                args.web, args.styles, args.config, args.all]):
        parser.print_help()
        return
    
    if args.all or args.basic:
        example_basic_usage()
    
    if args.all or args.production:
        example_production_usage()
    
    if args.all or args.run_async:
        asyncio.run(example_async_usage())
    
    if args.all or args.styles:
        example_style_comparison()
    
    if args.all or args.config:
        example_config_override()
    
    if args.all or args.web:
        example_web_automation()
    
    print("\n=== All examples completed ===")


if __name__ == "__main__":
    # Need random for some examples
    import random
    main()
