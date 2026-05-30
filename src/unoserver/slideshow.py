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

        self.document = self.desktop.loadComponentFromURL(
            url, "_blank", 0, ()
        )

        # Get presentation
        self.presentation = self.document.getPresentation()
        self.session_id = f"slideshow_{int(time.time())}_{id(self)}"
        logger.info(f"Loaded presentation. Session ID: {self.session_id}")
        return self.session_id

    def start(self, options: Dict[str, Any]) -> bool:
        """Start the slideshow with given options."""
        if not self.presentation:
            raise RuntimeError("No presentation loaded")

        # Build presentation properties
        props = []

        # Fullscreen
        props.append(PropertyValue("IsFullscreen", 0, True, 0))

        # Start from specific slide
        if start_slide := options.get("start_slide"):
            props.append(PropertyValue("StartSlide", 0, start_slide - 1, 0))

        # Loop
        if options.get("loop", False):
            props.append(PropertyValue("IsLooping", 0, True, 0))

        # TODO: Presenter console / dual screen support in future

        self.presentation.start(props)
        self.is_running = True
        logger.info(f"Slideshow started (session {self.session_id})")
        return True

    def next(self):
        if self.presentation:
            self.presentation.getController().gotoNextSlide()

    def previous(self):
        if self.presentation:
            self.presentation.getController().gotoPreviousSlide()

    def goto_slide(self, index: int):
        if self.presentation:
            self.presentation.getController().gotoSlide(index)

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