
"""A library designed to be used by OBS scripts, with a more pythonic interface
to OBS functionality.

NOTE: You must call obs.unload() in your script_unload callback.
If you aren't doing anything else in that callback, this can be done simply with:
	script_unload = obs.unload
"""


import weakref

import obspython


def unload():
	for resource in Resource.instances:
		resource.release()


class Resource(object):
	"""Common code for all resource-like objects

	Call obs methods for the resource easily:
		resource.method(arg) -> obspython.obs_TYPE_METHOD(resource, arg)

	Automatically releases the reference (if ref counted) on GC or unload().
	Can explicitly release with resource.release() or on exit if used as a context manager.
	"""

	# Track all Resource instances with a weak reference so we can find them from unload()
	instances = weakref.WeakSet()

	# The name as used in obs methods, eg. obs_NAME_release()
	# Leave none to default to cls.__name__.lower().
	type_name = None

	def __init__(self, reference):
		self._reference = reference
		self.instances.add(self)
		if self.type_name is None:
			self.type_name = type(self).__name__.lower()

	@property
	def reference(self):
		if self._reference is None:
			raise Exception(f"Reference to {self.type_name} used after being released")
		return self._reference

	# Override name property to customise __str__ representation,
	# defaults to just the reference __str__
	@property
	def name(self):
		return self._reference

	def __str__(self):
		return f"<{type(self).__name__} {self.name}>"
	__repr__ = __str__

	def release(self):
		if self._reference is not None:
			self.get_method('release')()
			self._reference = None

	def __getattr__(self, attr):
		return self.get_method(attr)

	def get_method(self, name):
		method = getattr(obspython, f'obs_{self.type_name}_{name}')
		def bound_method(*args):
			return method(self.reference, *args)
		return bound_method

	def __del__(self):
		self.release()

	def __enter__(self):
		return self

	def __exit__(self, *exc_info):
		self.release()


class Source(Resource):
	@classmethod
	def list(cls):
		return [cls(ref) for ref in obspython.obs_enum_sources()]

	@property
	def name(self):
		return self.get_name()
