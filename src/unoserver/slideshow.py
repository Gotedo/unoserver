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

        # 1. Dynamically Disable the Presenter Console Extension
        try:
            smgr = self.ctx.ServiceManager
            provider = smgr.createInstanceWithContext(
                "com.sun.star.configuration.ConfigurationProvider", self.ctx
            )
            from com.sun.star.beans import PropertyValue
            node = PropertyValue("nodepath", 0, "/org.openoffice.Office.PresenterScreen/PresenterScreenSettings", 0)
            update_access = provider.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationUpdateAccess", (node,)
            )
            update_access.setPropertyValue("Enabled", False)
            update_access.commitChanges()
            logger.info("Presenter Console dynamically disabled.")
        except Exception as e:
            logger.debug(f"Could not disable Presenter Console (may not be installed): {e}")

        # 2. Load the document normally (Do NOT use Hidden=True, it causes black screens)
        url = uno.systemPathToFileUrl(path)
        load_props = (PropertyValue("ReadOnly", 0, True, 0),)
        
        self.document = self.desktop.loadComponentFromURL(url, "_blank", 0, load_props)
        if self.document is None:
            raise RuntimeError("LibreOffice could not find or load the document.")

        # 3. Hide the main Editor window entirely
        try:
            frame = self.document.getCurrentController().getFrame()
            window = frame.getContainerWindow()
            window.setVisible(False)
        except Exception as e:
            logger.warning(f"Could not hide editor window: {e}")

        self.presentation = self.document.getPresentation()
        if self.presentation is None:
            raise RuntimeError("Loaded document is not a presentation")

        self.session_id = f"ss_{int(time.time())}_{id(self)}"
        logger.info(f"Successfully loaded presentation. Session ID: {self.session_id}")
        return self.session_id

    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow or connect to the already running controller."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        try:
            # Call start to ensure the engine is running (safe to call if already started by --show)
            self.presentation.start()

            # Wait for the controller to become available
            controller = None
            for _ in range(10): # Poll for 5 seconds
                time.sleep(0.5)
                controller = self.presentation.getController()
                if controller is not None:
                    break

            if controller is None:
                raise RuntimeError("Slideshow started, but controller never became ready.")

            if start_slide := options.get("start_slide"):
                try:
                    controller.gotoSlide(int(start_slide) - 1)
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
        """Jump to specific slide (0-based)"""
        if not self.presentation:
            return
        try:
            controller = self.presentation.getController()
            if controller:
                controller.gotoSlide(index)
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