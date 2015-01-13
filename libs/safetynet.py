
"""A context manager that will capture errors and drop into an interactive console for debugging

To facilitate use in debugging, can be run directly:
	python -m safetynet "FILEPATH" [ARGS]
to run FILEPATH under a SafetyNet.
"""

import sys
import traceback
from code import InteractiveConsole


class SafetyNet(object):
	"""By wrapping code in a safety net, the application will fall back to an interactive console
	should the code raise an Exception. Note BaseException and friends are ignored.
	Console has some magic locals:
		'ex' - The exception object.
		'tb' - The traceback object.
		'logger' - The SafetyNet logger object (or None).
		'fr0', 'fr1', ... - These are special frame objects. By accessing their attributes, you can
			read their locals or globals (Note that closures aren't supported by this method).
			Frames are counted upwards (most recent call first) from zero.
		'frames' - This is the list fr0, fr1, ...
	Usage:
		with SafetyNet():
			x = 0
			print 1/x # Oh shit
		>>> print ex
		ZeroDivisionError: integer division or modulo by zero
		>>> print fr0.x
		0

	Obviously, this is not intended for production code, but should be useful when debugging.
	
	"""
	def __enter__(self):
		caller = sys._getframe(1)
		self.banner = "SafetyNet at {}:{}({}) caught exception. Entering debug console.".format(
		              caller.f_code.co_filename, caller.f_lineno, caller.f_code.co_name)

	def __exit__(self, ex_type, ex, tb):
		if not isinstance(ex, Exception):
			return # BaseException or None (no error)
		traceback.print_exc()
		frames = get_frames(tb)
		locals = dict(ex=ex, tb=tb, frames=frames)
		locals.update({'fr{}'.format(i): frame for i, frame in enumerate(frames)})
		InteractiveConsole(locals=locals).interact(banner=self.banner)
		return True


class WrappedFrame(object):
	"""A magic wrapper around a frame object that can look up locals and globals when you
	access its attributes."""
	def __init__(self, frame):
		self._frame = frame

	def __getattr__(self, attr):
		if hasattr(self._frame, attr):
			return getattr(self._frame, attr)
		elif attr in self._frame.f_locals:
			return self._frame.f_locals[attr]
		elif attr in self._frame.f_globals:
			return self._frame.f_globals[attr]
		else:
			raise AttributeError

	def __str__(self):
		return "<Frame at %s:%d(%s)>" % (self.f_code.co_filename, self.f_lineno, self.f_code.co_name)


def get_frames(tb):
	"""Given a tb, returns a list of WrappedFrame objects."""
	while tb.tb_next:
		tb = tb.tb_next
	frames = []
	f = tb.tb_frame
	while f:
		frames.append(WrappedFrame(f))
		f = f.f_back
	return frames


if __name__ == '__main__':
	if len(sys.argv) > 1:
		filepath = sys.argv[1]
		sys.argv = sys.argv[1:]
		with SafetyNet():
			execfile(filepath)
	else:
		print "USAGE: {} FILEPATH".format(sys.argv[0])
