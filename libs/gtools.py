
"""Miscellaneous tools for debugging and working with gevent"""

__REQUIRES__ = ['gevent']

import signal

import gevent.backdoor
from gevent import sleep

def backdoor(port=1234):
	"""Start up a backdoor server on the local interface."""
	backdoor = gevent.backdoor.BackdoorServer(('localhost', port))
	backdoor.start()

def starve_test(callback=None, timeout=2, interval=0.1):
	"""Keep a SIGALRM perpetually pending...as long as we get rescheduled in a timely manner.
	timeout: How long we can be not scheduled before triggering.
	interval: How often we try to reset the timer (this must be less than timeout)
	callback: What to do when we trigger. There are several options:
	          If callback is an Exception, raise it.
	          Otherwise, call it with no args.
	          NOTE: This is run in a raw signal handler (NOT a gevent signal handler)
	          so if it raises then it will raise in the context of whatever greenlet is running.
	          Default: Raise an Exception().
	This function does not return, and may trigger multiple times.
	"""
	if callback is None:
		callback = Exception("Greenlets being starved")
	def boom(sig, frame):
		if isinstance(callback, BaseException) or issubclass(callback, BaseException):
			raise callback
		callback()
	signal.signal(signal.SIGALRM, boom)
	while 1:
		signal.alarm(2)
		sleep(0.1)
