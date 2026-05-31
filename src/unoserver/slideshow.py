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
from typing import Any, Dict, Optional

from com.sun.star.presentation import XPresentation2
from com.sun.star.frame import XController
from com.sun.star.beans import PropertyValue

logger = logging.getLogger("unoserver.slideshow")


class UnoSlideshow:
    """Manages a single long-running LibreOffice slideshow session."""

    def __init__(self, uno_port: str = "2002"):
        self.uno_port = uno_port
        self.ctx = None
        self.desktop = None
        self.document = None
        self.presentation: Optional[XPresentation2] = None
        self.controller = None
        self.session_id = None
        self.is_running = False

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

    def load_presentation(self, path: str) -> str:
        """Connect to LibreOffice, hide UI elements, and load the presentation."""
        if not self.ctx:
            self._connect()

        # 1. Universally Disable the Presenter Console Extension
        try:
            # Get the default configuration provider via singleton
            cp = self.ctx.getValueByName(
                "/singletons/com.sun.star.configuration.theDefaultProvider"
            )
            
            from com.sun.star.beans import PropertyValue
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

        # 2. Load the document normally (Do NOT use Hidden=True, it causes black screens)
        import uno
        url = uno.systemPathToFileUrl(path)
        load_props = (PropertyValue("ReadOnly", 0, True, 0),)
        
        self.document = self.desktop.loadComponentFromURL(url, "_blank", 0, load_props)
        if self.document is None:
            raise RuntimeError("LibreOffice could not find or load the document.")

        # 3. Move the main Editor window off-screen to avoid focus bugs
        try:
            frame = self.document.getCurrentController().getFrame()
            window = frame.getContainerWindow()
            # Keep window on-screen to prevent macOS thread suspension, 
            # but make it virtually invisible (1x1 pixel in the top left corner).
            window.setPosSize(0, 0, 1, 1, 15)
        except Exception as e:
            logger.warning(f"Could not move editor window off-screen: {e}")

        self.presentation = self.document.getPresentation()
        if self.presentation is None:
            raise RuntimeError("Loaded document is not a presentation")

        # Fallback safeguard: Force the presentation engine to use Display 1
        try:
            self.presentation.setPropertyValue("Display", 1)
        except Exception as e:
            logger.debug(f"Could not lock display property: {e}")

        self.session_id = f"ss_{int(time.time())}_{id(self)}"
        logger.info(f"Successfully loaded presentation. Session ID: {self.session_id}")
        return self.session_id

    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow or connect to the already running controller."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        import platform
        import subprocess
        import time

        try:
            # Force the LibreOffice engine to wake up and request OS focus BEFORE starting
            # This cures the "black screen waiting for click" issue.
            try:
                frame = self.document.getCurrentController().getFrame()
                window = frame.getContainerWindow()
                window.toFront()
                window.setFocus()
            except Exception as e:
                logger.debug(f"Could not focus window: {e}")

            # Force the presentation to render on top of everything
            try:
                self.presentation.setPropertyValue("IsAlwaysOnTop", True)
            except Exception as e:
                logger.debug(f"Could not set IsAlwaysOnTop: {e}")

            # Start the presentation
            self.presentation.start()

            # OS-LEVEL OVERRIDE FOR MACOS BLACK SCREEN
            # We must force macOS to make LibreOffice the active application, 
            # otherwise the slideshow engine stays paused and never creates the controller.
            if platform.system() == "Darwin":
                try:
                    # Give the window server a split second to register the new fullscreen window
                    time.sleep(0.5) 
                    subprocess.run(
                        ["osascript", "-e", 'tell application "LibreOffice" to activate'],
                        check=False,
                        capture_output=True
                    )
                    logger.info("macOS Focus Override triggered via osascript.")
                except Exception as e:
                    logger.debug(f"macOS activation failed: {e}")

            # Wait for the controller to become available
            slideShowController = None
            for _ in range(60): # Poll for 30 seconds
                time.sleep(0.5)
                slideShowController = self.presentation.getController()
                if slideShowController is not None:
                    break

            if slideShowController is None:
                raise RuntimeError("Slideshow started, but controller never became ready.")

            # Now that the presentation has safely taken over the screen,
            # push the main editor window entirely off-screen so it's fully gone.
            try:
                frame = self.document.getCurrentController().getFrame()
                window = frame.getContainerWindow()
                window.setPosSize(-10000, -10000, 100, 100, 15)
            except Exception as e:
                logger.debug(f"Could not move editor window off-screen: {e}")

            # Jump to the requested slide safely
            # Fetch the actual XDrawPage object instead of passing an integer
            if start_slide := options.get("start_slide"):
                try:
                    target_idx = int(start_slide) - 1
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
                    # FIX: Pass the XDrawPage interface, not the integer
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
        if self.presentation:
            self.presentation.end()
            self.is_running = False
            logger.info(f"Slideshow ended (session {self.session_id})")

    def get_current_slide_index(self) -> int:
        if self.presentation and self.presentation.getController():
            return self.presentation.getController().getCurrentSlideIndex()
        return -1

    def get_slide_count(self) -> int:
        if self.document:
            return self.document.getDrawPages().getCount()
        return 0

    def close(self):
        """Clean up resources."""
        if self.document:
            self.document.close(True)
            self.document = None
        self.presentation = None
        self.is_running = False