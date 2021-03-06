
"""Tools for inspecting running greenlets and getting tracebacks"""

__REQUIRES__ = ['greenlet']

import functools
import gc
import traceback
import sys

import gevent.hub

from greenlet import greenlet

def get_stack(g):
	"""Returns a list of frames, with the innermost frame last, or None if not running."""
	frame = g.gr_frame
	if not frame:
		current = greenlet.getcurrent()
		if g is not current:
			return None # not running
		# the current greenlet has no saved frame object, use sys._getframe() instead.
		frame = sys._getframe()
	stack = []
	while frame:
		stack.append(frame)
		frame = frame.f_back
	return stack[::-1]


def get_tb(g):
	"""Takes a greenlet and returns a traceback string, or None if not running.
	"""
	stack = get_stack(g)
	if not stack: return
	tb = []
	for frame in stack:
		filename = frame.f_code.co_filename
		lineno = frame.f_lineno
		funcname = frame.f_code.co_name
		try:
			with open(filename) as f:
				line = f.read().split('\n')[lineno-1].strip()
		except (IOError, KeyError):
			line = None
		tb.append((filename, lineno, funcname, line))
	return ''.join(traceback.format_list(tb))


def get_greenlets():
	"""Fetch all greenlet instances from the garbage collector"""
	return [o for o in gc.get_objects() if isinstance(o, greenlet)]


def print_greenlet_tbs():
	"""Print all greenlets along with a traceback, or a short diagnostic (eg. <started but not running>)."""
	for g in get_greenlets():
		tb = get_tb(g)
		if tb:
			tb = tb.rstrip('\n')
		else:
			if not hasattr(g, 'started'):
				tb = "<unknown>"
			elif not g.started:
				tb = "<not started>"
			elif not g.ready():
				tb = "<started but not running>"
			elif g.successful():
				tb = "<finished with value {!r}>".format(g.value)
			else:
				tb = "<finished with exception {!r}>".format(g.exception)
		print "===== {g!r} =====\n{tb}".format(**locals())


def debug_loop_exit(fn):
	"""Calls wrapped fn unchanged, but if a LoopExit occurs, will print info on all current greenlets."""
	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except gevent.hub.LoopExit:
			print_greenlet_tbs()
			raise
	return wrapper
