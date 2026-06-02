from __future__ import annotations

try:
    import uno
except ImportError:
    raise ImportError(
        "Could not find the 'uno' library. This package must be installed with a Python "
        "installation that has a 'uno' library. This typically means you should install "
        "it with the same Python executable as your Libreoffice installation uses."
    )

import logging
import time
import threading
import platform
import subprocess
from typing import Any, Dict, Optional

from com.sun.star.presentation import XPresentation2
from com.sun.star.frame import XController
from com.sun.star.beans import PropertyValue

from screeninfo import get_monitors

logger = logging.getLogger("unoserver.slideshow")


class UnoSlideshow:
    """Manages a single long-running LibreOffice slideshow session."""

    def __init__(self, uno_port: str = "2002", pid: Optional[int] = None):
        self.uno_port = uno_port
        self.ctx = None
        self.desktop = None
        self.document = None
        self.presentation: Optional[XPresentation2] = None
        self.controller = None
        self.session_id = None
        self.is_running = False

        # Monitor Caching State
        self.monitors = []
        self._monitor_lock = threading.Lock()
        self._stop_monitor_event = threading.Event()
        self._monitor_thread = None

        # Fetch immediately on init so they are ready for the first start() call
        self._update_monitors()
        # Start the 10-second ticker thread
        self._start_monitor_ticker()

        self.pid = pid  # Store the explicit PID passed from the server

    def _connect(self):
        """Connect to LibreOffice UNO."""
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local
        )
        ctx = resolver.resolve(
            f"uno:socket,host=127.0.0.1,port={self.uno_port};urp;StarOffice.ComponentContext"
        )
        self.ctx = ctx
        self.desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx
        )

    def load_presentation(self, path: str, options: Dict[str, Any] = None) -> str:
        """Connect to LibreOffice, hide UI elements, and load the presentation."""
        options = options or {}
        if not self.ctx:
            self._connect()

        # 1. Universally Disable the Presenter Console Extension
        try:
            # Get the default configuration provider via singleton
            cp = self.ctx.getValueByName(
                "/singletons/com.sun.star.configuration.theDefaultProvider"
            )

            # Target the master switch for the Presenter Screen
            prop = PropertyValue("nodepath", 0, "/org.openoffice.Office.Impress/Misc/Start", 0)
            
            update_access = cp.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationUpdateAccess", (prop,)
            )
            
            # Disable it and commit changes
            update_access.setPropertyValue("EnablePresenterScreen", False)
            update_access.commitChanges()
            logger.info("Presenter Console globally disabled via configuration.")
        except Exception as e:
            logger.debug(f"Could not disable Presenter Console: {e}")

        # 2. Load the document normally (No size hacks, no Hidden=True)
        url = uno.systemPathToFileUrl(path)
        load_props = (PropertyValue("ReadOnly", 0, True, 0),)
        
        self.document = self.desktop.loadComponentFromURL(url, "_blank", 0, load_props)
        if self.document is None:
            raise RuntimeError("LibreOffice could not find or load the document.")

        # Move the main editor window to an alternate monitor
        # based on the target display coordinates provided in options.
        target_x = options.get("display_x")
        target_y = options.get("display_y")

        target_monitor = None
        alt_monitor = None
        
        with self._monitor_lock:
            current_monitors = list(self.monitors)

        if target_x is not None and target_y is not None:
            target_x_int, target_y_int = int(target_x), int(target_y)
            for m in current_monitors:
                if m.x <= target_x_int < m.x + m.width and m.y <= target_y_int < m.y + m.height:
                    target_monitor = m
                    break

        if not target_monitor and current_monitors:
            target_monitor = current_monitors[0]

        # Find an alternate monitor to stash the editor
        for m in current_monitors:
            if m.x != target_monitor.x and m.y != target_monitor.y:
                alt_monitor = m
                break
        
        # Fallback if only 1 monitor exists
        if not alt_monitor and current_monitors:
            alt_monitor = current_monitors[0]

        try:
            frame = self.document.getCurrentController().getFrame()
            window = frame.getContainerWindow()
            
            # Hide the window from the OS task switcher/view
            window.setVisible(False)
            
            if alt_monitor:
                # 15 is the PosSize flag (X | Y | WIDTH | HEIGHT)
                # Stash it on the alternate monitor scaled down
                window.setPosSize(
                    alt_monitor.x,
                    alt_monitor.y,
                    1,
                    1,
                    15
                )
                logger.debug(f"Editor window successfully hidden and moved to alternate monitor at x={alt_monitor.x}, y={alt_monitor.y}")
            else:
                # Fallback if screeninfo array was empty
                window.setPosSize(-10000, -10000, 1, 1, 15)
                logger.debug("Editor window successfully hidden and moved off-screen.")
        except Exception as e:
            logger.warning(f"Could not move editor window off-screen: {e}")

        self.presentation = self.document.getPresentation()
        if self.presentation is None:
            raise RuntimeError("Loaded document is not a presentation")

        self.session_id = f"ss_{int(time.time())}_{id(self)}"
        logger.info(f"Successfully loaded presentation. Session ID: {self.session_id}")
        return self.session_id

    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow using the GUI Dispatcher to prevent macOS window desync."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        try:
            # 1. Bring LibreOffice to the foreground BEFORE starting
            # The app must hold OS focus for the window/rendering pipeline to execute cleanly.
            if platform.system() == "Darwin" and self.pid:
                try:
                    script = f'''
                    tell application "System Events"
                        try
                            set target_proc to first process whose unix id is {self.pid}
                            set frontmost of target_proc to true
                        end try
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
                    time.sleep(0.5)
                    logger.debug(f"LibreOffice instance (PID {self.pid}) brought to foreground.")
                except Exception as e:
                    logger.debug(f"macOS PID activation failed: {e}")

            # 2. Force the presentation to render on top of everything
            try:
                self.presentation.setPropertyValue("IsAlwaysOnTop", True)
            except Exception as e:
                logger.debug(f"Could not set IsAlwaysOnTop: {e}")

            # Target specific display via coordinates
            if "display_x" in options and "display_y" in options:
                target_display = self._get_display_index_for_coords(
                    int(options["display_x"]), 
                    int(options["display_y"])
                )
                try:
                    # Apply the resolved 1-based integer index to LibreOffice
                    self.presentation.setPropertyValue("Display", target_display)
                    logger.info(f"Targeting slideshow to Display {target_display} for coords ({options['display_x']}, {options['display_y']})")
                except Exception as e:
                    logger.warning(f"Could not set Display property: {e}")
            else:
                # Default fallback if no coordinates are provided
                try:
                    self.presentation.setPropertyValue("Display", 1)
                except Exception:
                    pass

            # 3. THE DISPATCHER
            # Simulates a native UI interaction (pressing F5), which forces macOS 
            # to properly paint the window and prevents the black screen deadlock.
            try:
                frame = self.document.getCurrentController().getFrame()
                dispatch_helper = self.ctx.ServiceManager.createInstanceWithContext(
                    "com.sun.star.frame.DispatchHelper", self.ctx
                )
                # Fire the internal command for "Start Slideshow"
                dispatch_helper.executeDispatch(frame, ".uno:Presentation", "", 0, ())
                logger.debug("Slideshow triggered via UI Dispatcher.")
            except Exception as e:
                logger.warning(f"Dispatcher failed, falling back to UNO API: {e}")
                self.presentation.start()

            # 4. Consume options
            if loop := options.get("loop", False):
                try:
                    self.presentation.setPropertyValue("IsEndless", bool(loop))
                    # Seamless loop (0 seconds pause between restarts)
                    self.presentation.setPropertyValue("Pause", 0)
                except Exception as e:
                    logger.debug(f"Could not set IsEndless loop property: {e}")

            # 5. Wait for the controller to become available
            slideShowController = None

            # Extract target coordinates if available to drive hardware mouse targeting
            target_x = options.get("display_x")
            target_y = options.get("display_y")

            for i in range(30): # Poll for 15 seconds
                time.sleep(0.5)
                slideShowController = self.presentation.getController()
                if slideShowController is not None:
                    logger.info(f"Slideshow controller acquired successfully on attempt {i+1}.")
                    break

            if slideShowController is None:
                raise RuntimeError("Slideshow started, but controller never became ready.")

            # 6. Jump to the requested slide safely
            if start_slide := options.get("start_slide"):
                try:
                    target_idx = int(start_slide)
                    draw_pages = self.document.getDrawPages()
                    if 0 <= target_idx < draw_pages.getCount():
                        page = draw_pages.getByIndex(target_idx)
                        slideShowController.gotoSlide(page)
                except Exception as e:
                    logger.warning(f"Could not jump to slide {start_slide}: {e}")

            self.is_running = True
            return True

        except Exception as e:
            logger.error(f"Failed to start slideshow: {e}", exc_info=True)
            raise RuntimeError("Failed to start slideshow") from e

    def next(self):
        """Go to next slide"""
        if not self.presentation:
            return
        try:
            controller = self.presentation.getController()
            if controller:
                controller.gotoNextSlide()
            else:
                logger.warning("Controller not available for next_slide")
        except Exception as e:
            logger.warning(f"next_slide failed: {e}")


    def previous(self):
        """Go to previous slide"""
        if not self.presentation:
            return
        try:
            controller = self.presentation.getController()
            if controller:
                controller.gotoPreviousSlide()
            else:
                logger.warning("Controller not available for previous_slide")
        except Exception as e:
            logger.warning(f"previous_slide failed: {e}")


    def goto_slide(self, index: int):
        """Jump to specific slide (0-based) using the XDrawPage interface"""
        if not self.presentation:
            return
        try:
            controller = self.presentation.getController()
            if controller:
                draw_pages = self.document.getDrawPages()
                if 0 <= index < draw_pages.getCount():
                    # Pass the XDrawPage interface, not the integer
                    page = draw_pages.getByIndex(index)
                    controller.gotoSlide(page)
                else:
                    logger.warning(f"goto_slide failed: index {index} is out of bounds")
            else:
                logger.warning(f"Controller not available for goto_slide({index})")
        except Exception as e:
            logger.warning(f"goto_slide({index}) failed: {e}")

    def pause(self):
        if self.presentation:
            self.presentation.getController().pause()

    def resume(self):
        if self.presentation:
            self.presentation.getController().resume()

    def end(self):
        """End the slideshow, shut down background tickers, and destroy the document."""
        # Shut down the tick
        self.stop_monitor_ticker()

        if self.presentation:
            try:
                self.presentation.end()
            except Exception:
                pass
            self.is_running = False
            logger.info(f"Slideshow ended (session {self.session_id})")
        
        # Give macOS a split second to destroy the fullscreen space
        time.sleep(0.5)
        
        # Instantly and forcefully close the document so the LibreOffice 
        # engine drops all stale window hierarchies for the next run.
        if self.document:
            try:
                self.document.close(True)
            except Exception as e:
                logger.debug(f"Could not cleanly close document: {e}")
            self.document = None

    def get_current_slide_index(self) -> int:
        if self.presentation and self.presentation.getController():
            return self.presentation.getController().getCurrentSlideIndex()
        return -1

    def get_slide_count(self) -> int:
        if self.document:
            return self.document.getDrawPages().getCount()
        return 0

    def close(self):
        """Clean up resources and stop background threads."""
        # Stop the background monitor ticker instantly
        if hasattr(self, '_stop_monitor_event'):
            self._stop_monitor_event.set()
            if self._monitor_thread and self._monitor_thread.is_alive():
                # Give it a fraction of a second to shut down cleanly
                self._monitor_thread.join(timeout=0.5)

        # Existing UNO cleanup
        if self.document:
            self.document.close(True)
            self.document = None
        self.presentation = None
        self.is_running = False

    def get_settings(self) -> Dict[str, Any]:
        """Retrieve the current properties of the active presentation."""
        if not self.presentation:
            return {}
        try:
            return {
                "loop": self.presentation.getPropertyValue("IsEndless"),
                "pause": self.presentation.getPropertyValue("Pause"),
                "is_always_on_top": self.presentation.getPropertyValue("IsAlwaysOnTop")
            }
        except Exception as e:
            logger.warning(f"Could not fetch presentation settings: {e}")
            return {}

    def _update_monitors(self):
        """Fetch displays from the OS and safely update the cache."""
        try:
            fresh_monitors = get_monitors()
            
            # Use lock to safely update the shared list
            with self._monitor_lock:
                self.monitors = fresh_monitors
                
        except ImportError:
            logger.warning("screeninfo library not found. Run: pip install screeninfo")
            with self._monitor_lock:
                self.monitors = []
        except Exception as e:
            logger.warning(f"Error fetching monitors in background thread: {e}")

    def _start_monitor_ticker(self):
        """Starts a background thread that updates monitors every 10 seconds."""
        def ticker():
            while not self._stop_monitor_event.is_set():
                # wait() blocks for 10 seconds. If the stop event is triggered 
                # during those 10 seconds, it returns True and we break instantly.
                if self._stop_monitor_event.wait(10.0):
                    break
                self._update_monitors()

        # Set as daemon so it won't prevent Python from exiting if left orphaned
        self._monitor_thread = threading.Thread(target=ticker, daemon=True)
        self._monitor_thread.start()
        logger.debug("Monitor caching background ticker started.")

    def stop_monitor_ticker(self):
        """Forcefully and cleanly shut down the background monitor ticker thread."""
        if hasattr(self, '_stop_monitor_event') and not self._stop_monitor_event.is_set():
            logger.debug(f"Stopping monitor ticker thread for session: {self.session_id}")
            # Signal the event to break the wait loop immediately
            self._stop_monitor_event.set()

            # Join the thread to ensure it is dead before moving on
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1.0)
                logger.debug("Monitor ticker thread joined successfully.")

    def __del__(self):
        """Ensure the background thread doesn't leak if the object is garbage collected."""
        try:
            self.stop_monitor_ticker()
        except Exception:
            pass

    def _update_monitors(self):
        """Fetch displays from the OS and safely update the cache."""
        try:
            from screeninfo import get_monitors
            fresh_monitors = get_monitors()
            
            # Use lock to safely update the shared list
            with self._monitor_lock:
                self.monitors = fresh_monitors
                
        except ImportError:
            logger.warning("screeninfo library not found. Run: pip install screeninfo")
            with self._monitor_lock:
                self.monitors = []
        except Exception as e:
            logger.warning(f"Error fetching monitors in background thread: {e}")

    def _start_monitor_ticker(self):
        """Starts a background thread that updates monitors every 10 seconds."""
        def ticker():
            while not self._stop_monitor_event.is_set():
                # wait() blocks for 10 seconds. If the stop event is triggered 
                # during those 10 seconds, it returns True and we break instantly.
                if self._stop_monitor_event.wait(10.0):
                    break
                self._update_monitors()

        # Set as daemon so it won't prevent Python from exiting if left orphaned
        self._monitor_thread = threading.Thread(target=ticker, daemon=True)
        self._monitor_thread.start()
        logger.debug("Monitor caching background ticker started.")

    def _get_display_index_for_coords(self, x: int, y: int) -> int:
        """
        Finds the 1-based LibreOffice display index containing the (x, y) coordinates
        using the cached monitor list.
        """
        # Safely read from the cache
        with self._monitor_lock:
            current_monitors = list(self.monitors)

        # Fallback to Display 1 if cache is empty (e.g., missing library)
        if not current_monitors:
            return 1

        min_dist = float('inf')
        nearest_index = 1

        # LibreOffice Display property is 1-based
        for i, m in enumerate(current_monitors, start=1):
            if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
                return i

            m_center_x = m.x + (m.width / 2)
            m_center_y = m.y + (m.height / 2)
            dist = abs(x - m_center_x) + abs(y - m_center_y)
            if dist < min_dist:
                min_dist = dist
                nearest_index = i

        return nearest_index