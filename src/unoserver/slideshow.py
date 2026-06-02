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

        # 2. Load the document normally (No size hacks, no Hidden=True)
        import uno
        url = uno.systemPathToFileUrl(path)
        load_props = (PropertyValue("ReadOnly", 0, True, 0),)
        
        self.document = self.desktop.loadComponentFromURL(url, "_blank", 0, load_props)
        if self.document is None:
            raise RuntimeError("LibreOffice could not find or load the document.")

        self.presentation = self.document.getPresentation()
        if self.presentation is None:
            raise RuntimeError("Loaded document is not a presentation")

        # 3. Fallback safeguard: Force the presentation engine to use Display 1
        try:
            self.presentation.setPropertyValue("Display", 1)
        except Exception as e:
            logger.debug(f"Could not lock display property: {e}")

        self.session_id = f"ss_{int(time.time())}_{id(self)}"
        logger.info(f"Successfully loaded presentation. Session ID: {self.session_id}")
        return self.session_id

    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow using the GUI Dispatcher to prevent macOS window desync."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        import platform
        import subprocess
        import time

        try:
            # 1. Bring LibreOffice to the foreground BEFORE starting
            # The app must hold OS focus for the Dispatcher command to execute cleanly.
            if platform.system() == "Darwin":
                try:
                    subprocess.run(
                        ["osascript", "-e", 'tell application "LibreOffice" to activate'],
                        check=False, capture_output=True
                    )
                    time.sleep(0.5) # Give macOS a moment to transition focus
                    logger.debug("LibreOffice brought to foreground.")
                except Exception as e:
                    logger.debug(f"macOS activation failed: {e}")

            # 2. Force the presentation to render on top of everything
            try:
                self.presentation.setPropertyValue("IsAlwaysOnTop", True)
            except Exception as e:
                logger.debug(f"Could not set IsAlwaysOnTop: {e}")

            # 3. THE DISPATCHER (The Fix)
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

            # 4. Wait for the controller to become available
            slideShowController = None
            for _ in range(30): # Poll for 15 seconds
                time.sleep(0.5)
                slideShowController = self.presentation.getController()
                if slideShowController is not None:
                    break

            if slideShowController is None:
                raise RuntimeError("Slideshow started, but controller never became ready.")

            # 5. HIDE THE EDITOR
            # Now that the presentation has safely taken over the screen, turn the editor invisible.
            try:
                frame = self.document.getCurrentController().getFrame()
                window = frame.getContainerWindow()
                window.setVisible(False)
                logger.debug("Editor window hidden successfully.")
            except Exception as e:
                logger.debug(f"Could not hide editor window: {e}")

            # 6. Jump to the requested slide safely
            if start_slide := options.get("start_slide"):
                try:
                    target_idx = int(start_slide) - 1 # Assuming start_slide is 1-indexed
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
        """End the slideshow and completely destroy the hidden document."""
        if self.presentation:
            try:
                self.presentation.end()
            except Exception:
                pass
            self.is_running = False
            logger.info(f"Slideshow ended (session {self.session_id})")
        
        # Give macOS a split second to destroy the fullscreen space
        import time
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
        """Clean up resources."""
        if self.document:
            self.document.close(True)
            self.document = None
        self.presentation = None
        self.is_running = False