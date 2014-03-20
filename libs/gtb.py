
"""Tools for inspecting running greenlets and getting tracebacks"""

__REQUIRES__ = ['greenlet']

import gc
import traceback

from greenlet import greenlet

def greenlet_tb(g):
	"""Takes a greenlet and returns a traceback string, or None if not running.
	Treats the currently active greenlet as a special case, but still returns the correct result.
	"""
	frame = g.gr_frame
	if not frame:
		current = greenlet.getcurrent()
		if g is not current:
			return None # not running
		# the current greenlet has no saved frame object, use traceback.format_stack instead.
		return ''.join(traceback.format_stack())
	stack = []
	while frame:
		filename = frame.f_code.co_filename
		lineno = frame.f_lineno
		funcname = frame.f_code.co_name
		try:
			with open(filename) as f:
				line = f.read().split('\n')[lineno-1].strip()
		except (IOError, KeyError):
			line = None
		stack.append((filename, lineno, funcname, line))
		frame = frame.f_back
	stack = stack[::-1]
	return ''.join(traceback.format_list(stack))

def get_greenlets():
	"""Fetch all greenlet instances from the garbage collector"""
	return [o for o in gc.get_objects() if isinstance(o, greenlet)]

def print_greenlet_tbs():
	"""Print all greenlets along with a traceback, or a short diagnostic (eg. <started but not running>)."""
	for g in get_greenlets():
		tb = greenlet_tb(g).rstrip('\n')
		if not tb:
			if not g.started:
				tb = "<not started>"
			elif not g.ready():
				tb = "<started but not running>"
			elif g.successful():
				tb = "<finished with value {!r}>".format(g.value)
			else:
				tb = "<finished with exception {!r}>".format(g.exception)
		print "===== {g!r} =====\n{tb}".format(**locals())

