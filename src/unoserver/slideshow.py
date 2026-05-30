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
        """Load a presentation document and return a session ID."""
        if not self.ctx:
            self._connect()

        url = uno.systemPathToFileUrl(path)
        logger.info(f"Attempting to load presentation: {path}")

        try:
            # Try multiple loading strategies - LibreOffice can be picky
            load_props_list = [
                (PropertyValue("Hidden", 0, False, 0),),           # Visible
                (PropertyValue("Hidden", 0, True, 0),),            # Hidden first
                (),                                                # No properties
            ]

            self.document = None
            for props in load_props_list:
                try:
                    self.document = self.desktop.loadComponentFromURL(
                        url, "_blank", 0, props
                    )
                    if self.document is not None:
                        break
                except Exception as inner_e:
                    logger.debug(f"Load attempt with props {props} failed: {inner_e}")

            if self.document is None:
                raise RuntimeError(f"LibreOffice could not load the document (returned None): {path}")

            # Verify it's a presentation
            self.presentation = self.document.getPresentation()
            if self.presentation is None:
                raise RuntimeError(f"Loaded document is not a presentation: {path}")

        except Exception as e:
            logger.error(f"Failed to load presentation {path}: {e}", exc_info=True)
            raise RuntimeError(f"Could not load presentation file: {path}") from e

        self.session_id = f"ss_{int(time.time())}_{id(self)}"
        logger.info(f"✅ Successfully loaded presentation. Session ID: {self.session_id}")
        return self.session_id


    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow with given options."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        logger.info(f"Starting slideshow for session {self.session_id}")

        try:
            # Give LibreOffice a moment to initialize the presentation
            time.sleep(1.5)

            # Modern LibreOffice: start() usually takes no arguments
            # We set initial state via controller instead
            controller = self.presentation.getController()

            if start_slide := options.get("start_slide"):
                try:
                    controller.gotoSlide(int(start_slide) - 1)
                except Exception as e:
                    logger.warning(f"Could not jump to slide {start_slide}: {e}")

            # Start the slideshow
            self.presentation.start()

            logger.info(f"✅ Slideshow started successfully (session {self.session_id})")
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