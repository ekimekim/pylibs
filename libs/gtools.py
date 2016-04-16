
"""Miscellaneous helpers and tools for using and debugging gevent"""

__REQUIRES__ = ['gevent']


import signal

import gevent
import gevent.queue
import gevent.event
import gevent.pool
import gevent.backdoor


def backdoor(port=1234, **kwargs):
	"""Start up a backdoor server on the local interface.
	Extra kwargs become local vars"""
	backdoor = gevent.backdoor.BackdoorServer(('localhost', port), locals=kwargs)
	backdoor.start()


def gmap(func, iterable, lazy=False):
	"""As per map(), but each func is run in a seperate greenlet. If lazy, as per imap() instead."""
	results = gevent.pool.Group().imap(func, iterable)
	if not lazy: results = list(results)
	return results


def gmap_unordered(func, iterable):
	"""As per gmap(), but always lazy and yields (arg, result) in order of completion."""
	iterable = list(iterable)
	queue = gevent.queue.Queue(len(iterable))
	def gen_callback(arg):
		def callback(g):
			queue.put((arg, g))
		return callback
	for arg in iterable:
		g = gevent.spawn(func, arg)
		g.link(gen_callback(arg))
	seen = 0
	while seen < len(iterable):
		arg, g = queue.get()
		seen += 1
		yield arg, g.get()


def get_first(*args):
	"""Begin executing all the given functions, returning whichever finishes first.
	All remaining greenlets are killed.
	If only one arg is given, it is treated as an iterable containing callables.
	Otherwise each arg should be callable.
	"""
	if not args:
		raise TypeError("Must give at least one argument to get_first()")
	if len(args) == 1:
		args, = args

	result = gevent.event.AsyncResult()
	def _get_first_wrapper(fn):
		try:
			result.set(fn())
		except Exception as ex:
			result.set_exception(ex)

	group = gevent.pool.Group()
	group.map_async(_get_first_wrapper, args)
	result.wait()
	group.kill(block=False)
	return result.get()


def get_all(*args):
	"""Execute all the given functions, blocking until they all return.
	The return values of each function are returned in the same order.
	If only one arg is given, it is treated as an iterable containing callables.
	Otherwise each arg should be callable.
	"""
	if len(args) == 1:
		args, = args
	return gmap(lambda fn: fn(), args)


def any(*args):
	"""Executes all the given functions, returning as soon as we can determine if any of the results are True
	If only one arg is given, it is treated as an iterable containing callables.
	Otherwise each arg should be callable.
	"""
	if len(args) == 1:
		args, = args
	for result in gmap_unordered(lambda fn: fn(), args):
		if result:
			return True
	return False


def all(*args):
	"""Executes all the given functions, returning as soon as we can determine if all of the results are True
	If only one arg is given, it is treated as an iterable containing callables.
	Otherwise each arg should be callable.
	"""
	if len(args) == 1:
		args, = args
	for result in gmap_unordered(lambda fn: fn(), args):
		if not result:
			return False
	return True


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
		gevent.sleep(0.1)


def track_switches(callback):
	"""Sets a profile function to watch for changes in current greenlet.
	Calls callback with new greenlet as arg."""
	greenlet = [None] # 1-length list lets us reference it without redefining it in inner block
	import gevent, sys
	def prof(frame, event, arg):
		newgreenlet = gevent.getcurrent()
		if greenlet[0] != newgreenlet:
			greenlet[0] = newgreenlet
			callback(greenlet[0])
	sys.setprofile(prof)
