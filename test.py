import mock
import random
import socket
import unittest

from selscrape import with_selenium
import selscrape

def open_listening_socket():
    for _ in range(10):
        port = random.randint(1025, 65535)
        sock = socket.socket()
        try:
            sock.bind(('localhost', port))
            sock.listen(1)
            return port, sock
        except socket.error:
            continue

GOOGLE = 'http://www.google.com'
class SelScrapeTest(unittest.TestCase):
    def test_basic(self):
        base_url = GOOGLE
        with with_selenium(base_url) as selenium:
            selenium.open('/')

    def test_display_clash(self):
        """We will find a free display if there is a clash"""
        colliding_display = ':73'
        displays = ([colliding_display] +
            [selscrape.pick_random_display() for _ in range(10)])

        with selscrape.with_proc(selscrape.start_headless_x,
                colliding_display) as _collision_x:
            with mock.patch('selscrape.pick_random_display',
                    lambda: displays.pop(0)):
                with with_selenium(GOOGLE) as selenium:
                    selenium.open('/')

    def test_port_clash(self):
        """We will find another free port if ports clash"""
        port, sock = open_listening_socket()
        ports = [port] + [selscrape.pick_random_port()
            for _ in range(10)]
        try:
            with mock.patch('selscrape.pick_random_port',
                    lambda: ports.pop(0)):
                with with_selenium(GOOGLE) as selenium:
                    selenium.open('/')
        finally:
            sock.close()

    def test_fail_out_clean(self):
        """Everything is cleaned up after failure"""
        try:
            with with_selenium(GOOGLE) as sel:
                raise Exception('Borken')
        except Exception:
            pass
        sel.X.wait()
        sel.selenium_server.wait()

if __name__ == '__main__':
    unittest.main()
