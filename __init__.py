"""
Robustly spawn Selenium servers in a headless X servers.

You may interact with these like normal seleniums but they do not an X
server to be running, and do not interfere with your screen.  The do
however require a more of less complete X install.

This library relies on the SELENIUM_SERVER_JAR environment variable
being the full path to the Selenium server jar.

For logging, use the print_logging function, or otherwise tweak the
'selscrape' logger.

Caveats:
   * Selenium is s l o w (particularly to start up)
   * Since selenium is slow you might like to cache selenium instances
"""

import logging
from selenium import selenium
from subprocess import Popen, PIPE
import contextlib
import os
import random
import threading
import time
import traceback
import Queue

logger = logging.getLogger('selscrape')
error, info, debug = logging.error, logging.info, logging.debug

def print_logging():
    logger.setLevel(logging.DEBUG)


# --- Utility functions ---

class Close(object):
    def __init__(self, stream):
        self.stream = stream

class MergedStream(object):
    """A stream that merges several other streams"""
    def __init__(self, *streams):
        # Stupid hack equivalent to select
        # which works on windows machines

        # Expensive, but easier than trying to do cross
        # platform select
        self.threads = []
        self.streams = list(streams)
        q = Queue.Queue()
        for stream in streams:
            t = threading.Thread(target=self.stream_pusher,
                args=(q, stream))
            t.daemon = True
            t.start()
            self.threads.append(t)
        self.q = q

    def readline(self):
        while self.streams:
            item = self.q.get()
            if isinstance(item, Close):
                self.streams.remove(item.stream)
            else:
                return item
        return ''

    @staticmethod
    def stream_pusher(q, stream):
        while True:
            line = stream.readline()
            if line == '':
                q.put(Close(stream))
                return
            else:
                q.put(line)

# IMPROVEMENT: These could be merged into one thread using poll... probably
def log_output(stream):
    """Read all output from a stream and write it to the logging library"""
    def inner():
        while True:
            line = stream.readline()
            if line == '':
                break
            else:
                debug(repr(line))
    t = threading.Thread(target=inner)
    t.daemon = True
    t.start()

@contextlib.contextmanager
def with_proc(spawn, *args):
    '''Spawn a process killing it on exit.'''
    p = spawn(*args)
    try:
        yield p
    finally:
        try:
            p.kill()
        finally:
            p.wait()

# --- Implementation ---

@contextlib.contextmanager
def with_selenium(base_url):
    """
    Starts a selenium client that talks to a headless Selenium Server.

    This creates a headless X server, a selenium server running in
    this X server, and a client connect to this server. The client is
    yielded form the context decorator. Example usage is as follows.

    with selenium_server('http://www.google.com/') as sel:
    	sel.open('/')

    All servers created are new and use distinct ports and displays,
    allowing this function to be called multiple times in parallel.
    """
    with with_proc(start_headless_x) as X:
        with with_proc(start_selenium_server, X.display) as server:
            sel = selenium("localhost", server.port, "*chrome", base_url)
            start_selenium(sel)
            sel.X = X
            sel.selenium_server = server
            try:
                yield sel
            finally:
                sel.stop()

def pick_random_display():
    return ':%d' % (random.randint(1, 400))

def start_headless_x(display=None):
    for _ in range(10):
        chosen_display = display if display else pick_random_display()
        headless_x = Popen(['Xvfb', chosen_display, '-ac'],
            stdout=PIPE, stderr=PIPE) # headless X
        headless_x.display = chosen_display
        time.sleep(0.5) # Give things time to crash
        if headless_x.poll() is not None:
            _, error = headless_x.communicate()
            if 'Server is already active' in error:
                info('Server already running on %r.'
                     'Retrying on different display', chosen_display)
            else:
                raise Exception('Xvfb failed to start :%r' % error)
        else:
            info('Brought up headless X on display %r with pid %r',
                 chosen_display, headless_x.pid)
            log_output(headless_x.stderr)
            log_output(headless_x.stdout)
            return headless_x
    else:
        raise Exception('Failed to find a free display'
            ' when spawning headless X')

def pick_random_port():
    return random.randint(1025, 65535)

def start_selenium_server(display=':99'):
    """Start a selenium server on a random port."""
    for _ in range(10):
        info('Bringing up selenium')
        port = pick_random_port()
        SELENIUM_SERVER_JAR = os.environ['SELENIUM_SERVER_JAR']
        sel_server = Popen(
            ['java', '-jar', SELENIUM_SERVER_JAR,
                '-port', str(port)],
            env=dict(os.environ, DISPLAY=display),
            stdout=PIPE, stderr=PIPE)

        # Stupid selenium takes an age to start. I can't really sleep
        # until I can tell it's done
        sel_server.port = port
        if wait_for_selenium_start(sel_server):
            return sel_server
        else:
            continue
    else:
        raise Exception('Failed to start selenium server')

def wait_for_selenium_start(sel_server):
    """Ensure that the selenium server starts correctly"""
    merged_stream = MergedStream(
        sel_server.stdout,
        sel_server.stderr)

    while True:
        line = merged_stream.readline()
        debug(repr(line))
        if line == '':
            raise Exception('Selenium server failed to start')
        elif 'Started SocketListener on' in line:
            log_output(merged_stream)
            info('Selenium server listening on %r with pid %r',
                 sel_server.port,
                 sel_server.pid)
            return True
        elif 'Selenium is already running on port' in line:
            info('Selenium is already running on port %r.'
                 ' Retrying on different port', sel_server.port)
            log_output(merged_stream)
            sel_server.wait()
            return False

def start_selenium(sel):
    """Start up a given selenium client. Retry on error"""
    for _ in range(10): # Wait for selenium to come up
        try:
            sel.start()
        except Exception:
            info('Failed to start selenium client retrying...')
            print traceback.format_exc()
            time.sleep(2)
        else:
            break
    else:
        raise Exception('Selenium failed to start')

__all__ = ['with_selenium', 'logger']
