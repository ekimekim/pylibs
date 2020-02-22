
"""A library designed to be used by OBS scripts, with a more pythonic interface
to OBS functionality.

NOTE: You must call obs.unload() in your script_unload callback.
If you aren't doing anything else in that callback, this can be done simply with:
	script_unload = obs.unload
"""


import weakref

import obspython


def unload():
	for releasable in Releasable.instances:
		releasable.release()


class Releasable(object):
	"""Mixin for objects that need to be released upon destruction
	or unload. Can also be explicitly released with release()
	or on exit when used as a context manager.

	Can check if already released with 'released' property.
	"""

	# Track all Releasable instances with a weak reference so we can find them from unload()
	instances = weakref.WeakSet()

	released = False

	def __init__(self):
		self.instances.add(self)

	def release(self):
		if self.released:
			return
		self._release()
		self.released = True

	def _release(self):
		"""Actually release the object"""
		raise NotImplementedError

	def __del__(self):
		self.release()

	def __enter__(self):
		return self

	def __exit__(self, *exc_info):
		self.release()


class Timer(Releasable):
	"""Repeating timer that triggers callback every INTERVAL seconds.
	Can also operate in a one-shot mode if repeat=False.
	"""
	def __init__(self, callback, interval, repeat=True):
		# OBS uses the python callable object as the timer id, so
		# we create a unique callable.
		def run():
			callback()
			if not repeat:
				self.release()
		self.run = run
		obspython.timer_add(self.run, int(interval * 1000))

	def _release(self):
		obspython.timer_remove(self.run)


class Resource(Releasable):
	"""Common code for all resource-like objects

	Call obs methods for the resource easily:
		resource.method(arg) -> obspython.obs_TYPE_METHOD(resource, arg)

	Automatically releases the reference (if ref counted) on GC or unload().
	Can explicitly release with resource.release() or on exit if used as a context manager.
	"""

	# The name as used in obs methods, eg. obs_NAME_release()
	# Leave none to default to cls.__name__.lower().
	type_name = None

	def __init__(self, reference):
		self._reference = reference
		if self.type_name is None:
			self.type_name = type(self).__name__.lower()
		super().__init__()

	@property
	def reference(self):
		if self.released:
			raise Exception(f"Reference to {self.type_name} used after being released")
		return self._reference

	# Override name property to customise __str__ representation,
	# defaults to just the reference __str__.
	@property
	def name(self):
		return self._reference

	def __str__(self):
		if self.released:
			return f"<{type(self).__name__} (RELEASED)>"
		else:
			return f"<{type(self).__name__} {self.name}>"
	__repr__ = __str__

	def _release(self):
		self.get_method('release')()

	def __getattr__(self, attr):
		return self.get_method(attr)

	def get_method(self, name):
		method = getattr(obspython, f'obs_{self.type_name}_{name}')
		def bound_method(*args):
			return method(self.reference, *args)
		return bound_method


class Source(Resource):
	@classmethod
	def list(cls):
		return [cls(ref) for ref in obspython.obs_enum_sources()]

	@property
	def name(self):
		return self.get_name()
