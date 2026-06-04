gotedo-unoserver
=========

Using LibreOffice as a server for converting and comparing documents, and running slideshows for presentations.

Overview
--------

Using LibreOffice to convert documents is easy, you can use a command like this to
convert a file to PDF, for example::

    $ libreoffice --headless --convert-to pdf ~/Documents/MyDocument.odf

However, that will load LibreOffice into memory, convert a file and then exit LibreOffice,
which means that the next time you convert a document LibreOffice needs to be loaded into
memory again.

To avoid that, LibreOffice has a listener mode, where it can listen for commands via a port,
and load and convert documents without exiting and reloading the software. This lowers the
CPU load when converting many documents with somewhere between 50% and 75%, meaning you can
convert somewhere between two and four times as many documents in the same time using a listener.

Unoserver contains three commands to help you do this, `gotedo_unoserver` which starts a listener on the
specified IP interface and port, and `gotedo_unoconverter` which will connect to a listener and ask it
to convert a document, as well as `gotedo_unocompare` which will connect to a listener and ask it
to compare two documents and convert the result document. There is also the `gotedo_unoping` command
that checks if a server is up and running, and prints its versions.


Installation
------------

NB! Windows and Mac support is as of yet untested.

Unoserver needs to be installed by and run with the same Python installation that LibreOffice uses,
to properly run the `gotedo_unoserver` command. For client/server installations, see below.

On Unix this usually means you can just install it with::

   $ sudo -H pip install gotedo-unoserver

If you have multiple versions of LibreOffice installed, you need to install it for each one.
Usually each LibreOffice install will have it's own `python` executable and you need to run
`pip` with that executable::

  $ sudo -H /full/path/to/python -m pip install gotedo-unoserver

To find all Python installations that have the relevant LibreOffice libraries installed,
you can run a script called `find_uno.py`::

  wget -O find_uno.py https://gist.githubusercontent.com/regebro/036da022dc7d5241a0ee97efdf1458eb/raw/find_uno.py
  python3 find_uno.py

This should give an output similar to this::

  Trying python found at /usr/bin/python3... Success!
  Trying python found at /opt/libreoffice7.1/program/python... Success!
  Found 2 Pythons with Libreoffice libraries:
  /usr/bin/python3
  /opt/libreoffice7.1/program/python

The `/usr/bin/python3` binary will be the system Python used for versions of
Libreoffice installed by the system package manager. The Pythons installed
under `/opt/` will be Python versions that come with official LibreOffice
distributions.

To install on such distributions, do the following::

  $ wget https://bootstrap.pypa.io/get-pip.py
  $ sudo /path/to/python get-pip.py
  $ sudo /path/to/python -m pip install gotedo-unoserver

You can also install it in a virtualenv, if you are using the system Python
for that virtualenv, and specify the ``--system-site-packages`` parameter::

  $ virtualenv --python=/usr/bin/python3 --system-site-packages virtenv
  $ virtenv/bin/pip install gotedo-unoserver

Windows and Mac installs aren't officially supported yet, but on Windows the
paths to the LibreOffice Python executable are usually in locations such as
`C:\\Program Files (x86)\\LibreOffice\\python.exe`. On Mac it can be for
example `/Applications/LibreOffice.app/Contents/python` or
`/Applications/LibreOffice.app/Contents/Resources/python`.


Usage
-----

Installing unoserver installs four scripts, `gotedo_unoserver`, `gotedo_unoconverter`, `gotedo_unocompare`
and `unoping`. The server can also be run as a module with `python3 -m gotedo_unoserver.server`,
with the same arguments as the main script, which can be useful as it must be run with
the LibreOffice provided Python.


Unoserver
~~~~~~~~~

.. code::

  gotedo_unoserver [-h] [-v] [--interface INTERFACE] [--uno-interface UNO_INTERFACE] [--port PORT] [--uno-port UNO_PORT]
            [--daemon] [--executable EXECUTABLE] [--user-installation USER_INSTALLATION]
            [-p/--libreoffice-pid-file LIBREOFFICE_PID_FILE] [--conversion-timeout CONVERSION_TIMEOUT]
            [--stop-after STOP_AFTER] [--verbose] [--quiet] [-f/--logfile logfile]

* `-v, --version`: Display version and exit.
* `--interface`: The interface used by the XMLRPC server, defaults to "127.0.0.1"
* `--port`: The port used by the XMLRPC server, defaults to "2003"
* `--uno-interface`: The interface used by the LibreOffice server, defaults to "127.0.0.1"
* `--uno-port`: The port used by the LibreOffice server, defaults to "2002"
* `--daemon`: Deamonize the server
* `--executable`: The path to the LibreOffice executable
* `--user-installation`: The path to the LibreOffice user profile, defaults to a dynamically created temporary directory
* `--p`, `--libreoffice-pid-file`: If set, unoserver will write the Libreoffice PID to this file.
  If started in daemon mode, the file will not be deleted when unoserver exits.
* `--conversion-timeout`: Terminate Libreoffice and exit if a conversion does not complete in the given time (in seconds).
* `--stop-after`: Terminate Libreoffice and exit after the given number of requests.
* `--verbose`: Add debug information as output
* `--quiet`: Only output errors and warnings
* `-f`, `--logfile`: Write logs to a file (defaults to stderr)


Unoconvert
~~~~~~~~~~

.. code::

  gotedo_unoconvert [-h] [-v] [--convert-to CONVERT_TO] [--input-filter INPUT_FILTER] [--output-filter OUTPUT_FILTER]
             [--filter-option FILTER_OPTIONS] [--update-index] [--dont-update-index] [--host HOST] [--port PORT]
             [--host-location {auto,remote,local}] [--protocol {http, https}] [-f/--logfile logfile] infile outfile

* `infile`: The path to the file to be converted (use - for stdin).
* `outfile`: The path to the converted file (use - for stdout).
* `--convert-to`: The file type/extension of the output file (ex pdf). Required when using stdout.
* `--input-filter`: The LibreOffice input filter to use (ex 'writer8'), if autodetect fails.
* `--output-filter`: The export filter to use when converting. It is selected automatically if not specified.
* `--filter-option`: Pass an option for the export filter, in name=value format, or for positional parameters, a comma separated list. Use true/false for boolean values. Can be repeated for multiple options.
* `--password`:
* `--host`: The host used by the server, defaults to "127.0.0.1".
* `--port`: The port used by the server, defaults to "2003".
* `--protocol`: What protocol to use to connect to the server (defaults to http).
* `--host-location`: The host location determines the handling of files. If you run the client on the
  same machine as the server, it can be set to local, and the files are sent as paths. If they are
  different machines, it is remote and the files are sent as binary data. Default is auto, and it will
  send the file as a path if the host is 127.0.0.1 or localhost, and binary data for other hosts.
* `-v`, `--version`: Display version and exit.
* `-f`, `--logfile`: Write logs to a file (defaults to stderr).
* `--verbose`: Increase informational output to logs.
* `--quiet`: Decrease informational output to logs.

Example for setting PNG width/height::

  gotedo_unoconvert infile.odt outfile.png --filter-options PixelWidth=640 --filter-options PixelHeight=480

Example for setting CSV output options::

  gotedo_unoconvert infile.xlsx outfile.csv --filter-options "59,34,76,1"

Example for HTML export with embedded images::

  gotedo_unoconvert infile.odt outfile.html --filter-options EmbedImages


Unocompare
~~~~~~~~~~

.. code::

  gotedo_unocompare [-h] [-v] [--file-type FILE_TYPE] [--host HOST] [--port PORT] [--protocol {http, https}]
             [--host-location {auto,remote,local}] [-f/--logfile logfile] oldfile newfile outfile

* `oldfile`: The path to the older file to be compared (use - for stdin).
* `newfile`: The path to the newer file to be compared (use - for stdin).
* `outfile`: The path to the result of the comparison and converted file (use - for stdout).
* `--file-type`: The file type/extension of the result output file (ex pdf). Required when using stdout
* `--host`: The host used by the server, defaults to "127.0.0.1".
* `--port`: The port used by the server, defaults to "2003".
* `--protocol`: What protocol to use to connect to the server (defaults to http).
* `--host-location`: The host location determines the handling of files. If you run the client on the
  same machine as the server, it can be set to local, and the files are sent as paths. If they are
  different machines, it is remote and the files are sent as binary data. Default is auto, and it will
  send the file as a path if the host is 127.0.0.1 or localhost, and binary data for other hosts.
* `-v, --version`: Display version and exit.
* `-f`, `--logfile`: Write logs to a file (defaults to stderr).
* `--verbose`: Increase informational output to logs.
* `--quiet`: Decrease informational output to logs.


Unoping
~~~~~~~

.. code::

  gotedo_unoping [-h] [-v] [--host HOST] [--port PORT] [--protocol {http,https}]
  [--verbose | --quiet] [-f LOGFILE]

* `--host`: The host used by the server, defaults to "127.0.0.1".
* `--port`: The port used by the server, defaults to "2003".
* `--protocol`: What protocol to use to connect to the server (defaults to http).
* `--host-location`: The host location determines the handling of files. If you run the client on the
  same machine as the server, it can be set to local, and the files are sent as paths. If they are
  different machines, it is remote and the files are sent as binary data. Default is auto, and it will
  send the file as a path if the host is 127.0.0.1 or localhost, and binary data for other hosts.
* `-v`, `--version`: Display version and exit.
* `-f`, `--logfile`: Write logs to a file (defaults to stderr).
* `--verbose`: Increase informational output to logs.
* `--quiet`: Decrease informational output to logs.

UnoSlideshow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `UnoSlideshow` infrastructure provides programmatic control over headful, hardware-accelerated presentation renderings. It allows independent clients to initialize slide transitions, query frame states, and drive displays cleanly across complex multi-monitor layouts.

Capabilities:
^^^^^^^^^^^^^

1. **Monitor Caching & Ticker Polling:** Upon initialization, the system safely interrogates the operating system topology via `screeninfo` and caches monitor coordinates. A background daemon thread manages a 10-second ticker to continually update the monitor geometry cache, allowing for instant zero-latency coordinate mappings when starting sessions. This ticker shuts down cleanly via an event cancel pattern during session destruction to prevent memory or thread leaks.

2. **Cross-Display Coordinate Resolution:**
   Clients do not pass arbitrary, brittle 1-based display integers. Instead, they pass absolute geometric layout coordinates (`display_x` and `display_y`). The module maps those values against its layout cache to target the proper display, securely handling complex physical arrangements—including secondary screens running in negative coordinate spaces (e.g., positioned to the left of the primary display).

3. **Isolated Multi-Session Orchestration:**
   By combining unique `user_installation` variables per `UnoServer` runtime with specific XML-RPC session ids (`session_id`), the architecture handles fully independent, concurrent slideshows executing on separate ports and monitors simultaneously without cross-process pollution.

.. note::
   **CONCURRENT SLIDESHOWS ON MACOS:**
   When orchestrating multiple concurrent slideshows on macOS, a timing issue within the macOS WindowServer may cause secondary instances to render as a black window. 

   To resolve this manually, the user is required to click on the black window in order to activate the slideshow. No automated interventions has worked so far.


Slideshow Management
--------------------

Unoserver provides a dedicated module for managing long-running LibreOffice slideshow sessions. This is designed for applications that need programmatic control over presentations, including multi-monitor targeting and real-time navigation.

To use the slideshow functionalities, initialize an ``UnoClient`` and connect to a running server port.

.. code-block:: python

    from gotedo_unoserver.client import UnoClient
    from gotedo_unoserver.server import UnoServer

    # Create a server
    server = UnoServer(user_installation=install_url_1, port="2003", uno_port="2004")
    # Pass in a specific LibreOffice executable (optional)
    # Important: Mark the session as `headful`
    server.start(executable=executable, headless=False)

    # Connect to the server managing the presentation
    client = UnoClient(server="127.0.0.1", port="2003")

    # 1. Load a Presentation
    # You can target specific displays using X/Y coordinates. 
    # Unoserver will automatically map this to the correct physical monitor.
    options = {
        "display_x": 1920,  # X-coordinate of the target monitor
        "display_y": 0,     # Y-coordinate of the target monitor
        "start_slide": 0    # 0-based index
    }
    
    # Returns a unique session ID for the loaded document
    session_id = client.load_presentation("/path/to/presentation.odp")

    # 2. Start the Slideshow
    client.start_slideshow(session_id, options)

    # 3. Navigation and Control
    client.next_slide(session_id)
    client.previous_slide(session_id)
    
    # Jump to a specific slide (0-based index)
    client.goto_slide(session_id, 4)

    # 4. Teardown
    client.stop_slideshow(session_id)


Resource Telemetry (RPC)
------------------------

When running automated or long-lived presentation processes, you may want to track system overhead. Unoserver exposes a lightweight, non-blocking XML-RPC method to poll the CPU and memory usage of the underlying LibreOffice process.

The telemetry engine runs in a background thread, aggregating resource data into rolling windows to ensure the RPC fetch remains lightning-fast and doesn't block your client application.

.. code-block:: python

    from gotedo_unoserver.client import UnoClient

    # Connect to the server managing the presentation
    # The port specified here is the XML-RPC server port
    client = UnoClient(server="127.0.0.1", port="2003")

    # Fetch the resource usage by passing the underlying LibreOffice UNO port
    # Note: Pass the UNO port (e.g., 2002), not the XML-RPC server port (e.g., 2003)
    usage = client.get_usage(target_port="2002")

    if usage:
        print(usage["5s"])   # Average over the last 5 seconds
        print(usage["15s"])  # Average over the last 15 seconds
        print(usage["60s"])  # Average over the last 1 minute

**Response Payload:**

If the process is running and tracked, the method returns a dictionary containing the ``5s``, ``15s``, and ``60s`` summaries. If the process is dead or untracked, the values will be ``None``.

Each time window contains the following data points:

* ``cpu_percent`` *(float)*: The calculated CPU utilization percentage.
* ``mem_bytes`` *(int)*: The Resident Set Size (RSS) memory in bytes.
* ``mem_percent`` *(float)*: The percentage of total system memory used by the process.

.. code-block:: python

    # Example Response
    {
        "5s": {
            "cpu_percent": 12.5,
            "mem_bytes": 145829888, 
            "mem_percent": 0.8
        },
        "15s": { ... },
        "60s": { ... }
    }

Client/Server installations
---------------------------

If you are installing Unoserver on a dedicated machine (virtual or not) to do the conversions and
are running the commands from a different machine, or if you want to call the convert/compare commands
from Python directly, the clients do not need access to Libreoffice. You can therefore follow the
instructions above to make Unoserver have access to the LibreOffice library, but on the client
side you can simply install Unoserver as any other Python library, with `python -m pip install gotedo-unoserver`
using the Python you want to use as the client executable.

Please note that there is no security on either ports used, and as a result Unoserver is vulnerable
to DDOS attacks, and possibly worse. The ports used **must not** be accessible to anything outside the
server stack being used.

Unoserver is designed to be started by some service management software, such as Supervisor or similar,
that will restart the service should it crash. Unoserver does not try to restart LibreOffice if it
crashes, but should instead also stop in that sitution. The ``--conversion-timeout`` argument will
teminate LibreOffice if it takes to long to convert a document, and that termination will also result
in Unoserver quitting. Because of this service monitoring software should be set up to restart
Unoserver when it exits.

---

### Development and Testing

To run the tests, you **must** use a Python environment tied to the interpreter bundled with LibreOffice, because it includes the required binary `uno` library bindings.

#### 1. Download and Install LibreOffice

* Download the latest stable version of **LibreOffice** from the official website:
[https://www.libreoffice.org/download/download-libreoffice/](https://www.libreoffice.org/download/download-libreoffice/)
* Install it normally on your system.

#### 2. Clone the Fork

.. code::

git clone https://github.com/gotedo/unoserver.git
cd unoserver


#### 3. Set Up and Activate the Python Virtual Environment (ve)

Instead of targeting LibreOffice's deeply nested Python executable for every command, we create an isolated virtual environment (`ve`) powered directly by LibreOffice's native engine.

**macOS:**

.. code::

# Define path to LibreOffice's internal Python
LO_PYTHON="$HOME/LibreOffice.app/Contents/Resources/python"

# Create the virtual environment named 've'
"$LO_PYTHON" -m venv ve

# Activate the virtual environment
source ve/bin/activate


**Windows (PowerShell):**

.. code::

# Define path to LibreOffice's internal Python
$LO_PYTHON = "$env:USERPROFILE\LibreOffice\program\python.exe"

# Create the virtual environment named 've'
& $LO_PYTHON -m venv ve

# Activate the virtual environment
.\ve\Scripts\Activate.ps1


.. critical::
   **CRITICAL NOTE FOR MACOS USER LOGOUTS:**

   If you log out of macOS or restart your system to apply settings, your terminal session will close. When you open a new terminal window, you **must re-activate the virtual environment** before running your tests or server instances:

   .. code-block:: bash

      cd unoserver
      source ve/bin/activate

#### 4. Install Dependencies inside the Activated Environment

Once your virtual environment is active, your terminal's standard `python` and `pip` commands point directly to LibreOffice's runtime. You no longer need to pass binary absolute paths.

.. code::

# Install development and testing dependencies (pytest, screeninfo, etc.)
pip install -e ".[devenv]" --no-build-isolation --no-warn-script-location


#### 5. Run the Tests

With the virtual environment (`ve`) activated, execution commands are clean, cross-platform, and direct:

**Run all tests:**

.. code::

python -m pytest tests -q


**Run only slideshow tests:**

.. code::

python -m pytest tests/test_slideshow.py -q --tb=no


**Run a specific test:**

.. code::

python -m pytest tests/test_slideshow.py::test_multiple_concurrent_slideshows -q --tb=short -s


#### 6. Optional: Create Helper Aliases

If you regularly open new shells and want to skip typing activation paths, you can add shortcuts to your shell configuration files.

**macOS (add to `~/.zshrc` or `~/.bash_profile`):**

.. code::

alias unove='cd ~/gotedo/unoserver && source ve/bin/activate'


Then, in any fresh terminal window (even after an OS logout), you can instantly prepare your context by executing:

.. code::

unove


#### Platform-Specific Notes

* **macOS**: If you get permission/quarantine issues when LibreOffice windows attempt to map screen contexts, run:
.. code::

xattr -r -d com.apple.quarantine ~/LibreOffice.app


* **Windows**: Always use **PowerShell** (not Command Prompt) for executing these environment steps.
* **Test Files**: Make sure these files exist in `tests/documents/`:
* `presentation_test.odp`
* `presentation_test.ppt`
* `presentation_test.pptx`

---

This version is complete, beginner-friendly, and includes all the lessons we learned during debugging. Would you like me to also add a small helper script (`run_slideshow_tests.sh` / `.ps1`) to make this even easier?


Comparison with `gotedo_unoconv`
-------------------------

Unoserver started as a rewrite, and hopefully a replacement to `gotedo_unoconv`, a module with support
for using LibreOffice as a listener to convert documents.

Differences for the user
~~~~~~~~~~~~~~~~~~~~~~~~

* Easier install for system versions of LibreOffice. On Linux, the packaged versions of LibreOffice
  typically uses the system Python, making it easy to install `gotedo-unoserver` with a simple
  `sudo pip install gotedo-unoserver` command.

* Separate commands for server and client. The client no longer tries to start a listener and then
  close it after conversion if it can't find a listener. Instead the new `gotedo_unoconverter` client
  requires the `gotedo_unoserver` to be started. This makes it less practical for one-off converts,
  but as mentioned that can easily be done with LibreOffice itself.

* The `gotedo_unoserver` listener does not prevent you from using LibreOffice as a normal user, while the
  `gotedo_unoconv` listener would block you from starting LibreOffice to open a document normally.

* You should be able to on a multi-core machine run several `gotedo_unoservers` with different ports.
  There is however no support for any form of load balancing in `gotedo_unoserver`, you would have to
  implement that yourself in your usage of `gotedo_unoconverter`. For performant multi-core scaling, it
  is necessary to specify unique values for each `gotedo_unoserver`'s `--port` and `--uno-port` options.

* Only LibreOffice is officially supported. Other variations are untested.


Differences for the maintainer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* It's a complete and clean rewrite, supporting only Python 3, with easier to understand and
  therefore easier to maintain code, hopefully meaning more people can contribute.

* It doesn't rely on internal mappings of file types and export filters, but asks LibreOffice
  for this information, which will increase compatibility with different LibreOffice versions,
  and also lowers maintenance.
