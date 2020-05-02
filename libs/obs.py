
"""A library designed to be used by OBS scripts, with a more pythonic interface
to OBS functionality.

NOTE: You must call obs.unload() in your script_unload callback.
If you aren't doing anything else in that callback, this can be done simply with:
	script_unload = obs.unload
"""


import weakref
import json

import obspython


def unload():
	for releasable in Releasable.instances():
		releasable.release()


class Releasable(object):
	"""Mixin for objects that need to be released upon destruction
	or unload. Can also be explicitly released with release()
	or on exit when used as a context manager.

	Can check if already released with 'released' property.
	"""

	# For some types, we want to automatically release when they're no longer used.
	# For others (eg. a timer), user expectation is that they remain existing in the background.
	# We switch behaviour by controlling whether our references to them are weak or strong.
	use_weak_refs = True

	# Track all Releasable instances with a (optionally weak) reference
	# so we can find them from unload()
	weak_instances = weakref.WeakSet()
	strong_instances = set()

	@classmethod
	def instances(cls):
		return cls.weak_instances | cls.strong_instances

	released = False

	def __init__(self):
		if self.use_weak_refs:
			self.weak_instances.add(self)
		else:
			self.strong_instances.add(self)

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


class Timer(object):
	"""Wraps a callback, giving options to call it periodically
	or once after an interval.
	Can be passed the callback directly:
		callback = Timer(10, callback)
	or used as a decorator:
		@Timer(10)
		def callback():
			...
	Note that the returned Timer object wraps the function,
	which can still be called normally, or have the timer functionality accessed:
		@Timer(10)
		def callback(flag=False):
			# Take a second longer to be called each time, or when manual_call() is called
			callback.set_interval(callback.interval + 1)

		def manual_call():
			callback(flag=True)
	"""

	callback = None
	raw_timer = None

	def __init__(self, interval, callback=None, repeat=True, start=True):
		"""Note that interval is in seconds and can be float.
		If callback is not given, expects to be used as a decorator and
		will not start until called with the callback.
		By default, will run every INTERVAL seconds. Pass repeat=False to only run once,
		after INTERVAL seconds.
		By default, will begin immediately. Disable this with start=False.
		"""
		self.interval = interval
		self.repeat = repeat
		self.start_immediately = start
		if callback:
			self(callback)

	def __str__(self):
		return f"<Timer calling {self.callback} after {self.repeat}s>"
	__repr__ = __str__

	def __call__(self, *args, **kwargs):
		if self.callback is None:
			(self.callback,) = args
			if self.start_immediately:
				self.start()
			return self
		else:
			return self.callback(*args, **kwargs)

	def _tick(self):
		self.callback()
		if not self.repeat:
			self.stop()

	def start(self):
		"""Start the timer. The first call will be in INTERVAL seconds."""
		if self.callback is None:
			raise Exception("Cannot start timer with no callback")
		if self.raw_timer is not None:
			raise Exception("Timer is already running")
		self.raw_timer = RawTimer(self._tick, self.interval)

	def stop(self):
		"""Stop the timer, preventing any further calls until re-started."""
		if self.raw_timer is not None:
			self.raw_timer.release()
			self.raw_timer = None

	def set_interval(self, interval):
		"""Change the timer interval to the new value.
		If the timer is currently running, it will continue with the next call
		in INTERVAL seconds.
		NOTE: With a running timer, changing interval mid-wait effectively resets the timer.
		For example, if a timer is set to fire in 10s, then you wait 5s, then change the interval
		to 15s, then it will fire 20s after the original start time, not 15s."""
		if self.raw_timer is not None:
			self.stop()
			self.interval = interval
			self.start()
		else:
			self.interval = interval


class RawTimer(Releasable):
	"""Repeating timer that triggers callback every INTERVAL seconds.
	This is a direct wrapper around OBS's timers. You probably want Timer()
	for a higher-level interface.
	"""
	use_weak_refs = False

	def __init__(self, callback, interval):
		# OBS uses the python callable object as the timer id, so
		# we create a unique callable.
		def run():
			callback()
		self.run = run
		obspython.timer_add(self.run, int(interval * 1000))

	def _release(self):
		obspython.timer_remove(self.run)


class Resource(object):
	"""Common code for all resource-like objects

	Call obs methods for the resource easily:
		resource.method(arg) -> obspython.obs_TYPE_METHOD(resource, arg)

	Automatically releases the reference (if ref counted) on GC or unload().
	See Releasable.
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
		if isinstance(self, Releasable) and self.released:
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
		"""Implement for Releasable, if we inherit from it"""
		self.get_method('release')()

	def __getattr__(self, attr):
		return self.get_method(attr)

	def get_method(self, name):
		method = getattr(obspython, f'obs_{self.type_name}_{name}')
		def bound_method(*args):
			return method(self.reference, *args)
		return bound_method


class Source(Resource, Releasable):
	@classmethod
	def list(cls):
		return [cls(ref) for ref in obspython.obs_enum_sources()]

	@classmethod
	def by_name(cls, name):
		"""Find the source with given unique name. Will ValueError if multiple exist,
		or KeyError if none do."""
		matches = [source for source in cls.list() if source.name == name]
		if len(matches) > 1:
			return matches[0] #raise ValueError(f"Multiple sources with name {name!r}")
		elif not matches:
			raise KeyError(f"No sources with name {name!r}")
		else:
			return matches[0]

	@property
	def name(self):
		return self.get_name()

	def get_settings(self):
		return Data(self.get_method('get_settings')())

	def properties(self):
		return Properties(self.get_method('properties')())

	def update(self, settings):
		if not isinstance(settings, Data):
			settings = Data.from_native(settings)
		self.get_method('update')(settings.reference)

	@property
	def settings(self):
		"""Helper for accessing or modifying settings.
		Context manager that gives a native settings object on entry,
		and updates the source if changes have been made to that object on successful exit.
		Example:
			with my_source.settings as s:
				s['text'] = 'new text'
		"""
		value = self.get_settings().to_native()
		class SourceSettingsManager(object):
			def __enter__(manager):
				return value
			def __exit__(manager, *exc_info):
				if exc_info == (None, None, None) and value != self.get_settings().to_native():
					self.update(value)
		return SourceSettingsManager()


class Data(Resource, Releasable):
	"""Data contains arbitrary JSON data.
	It can be converted to/from JSON or native python objects.

	It is recommended that you treat this as an opaque blob and convert
	it to native types for manipulation, as we do not have well-behaved wrappers
	for all the various type-specific functions
	"""

	@classmethod
	def from_json(cls, json_str):
		return cls(obspython.obs_data_create_from_json(json_str))

	@classmethod
	def from_native(cls, obj):
		return cls.from_json(json.dumps(obj))

	def to_json(self):
		return self.get_method('get_json')()

	def to_native(self):
		return json.loads(self.to_json())


class Properties(Resource):
	def first(self):
		"""Get first property. It does not appear to be possible to enumerate any property beyond the first."""
		return Property(self.get_method('first')())


class Property(Resource):
	def get_type(self):
		value = self.get_method('get_type')()
		return {
			# TODO others later
			6: 'list',
		}.get(value, f'unknown ({value})')

	def list_items(self):
		return [PropertyListItem(self, i) for i in range(self.list_item_count())]


class PropertyListItem(object):
	def __init__(self, property, index):
		self.property = property
		self.index = index

	def __getattr__(self, attr):
		return lambda: self.property.get_method(f'list_item_{attr}')(self.index)


class Scene(Resource, Releasable):
	@classmethod
	def current(cls):
		"""Returns current scene"""
		return cls(obspython.obs_scene_from_source(obspython.obs_frontend_get_current_scene()))

	def items(self):
		"""Returns list of scene items"""
		import logging
		return [SceneItem(item) for item in obspython.obs_scene_enum_items(self.reference)]


class SceneItem(Resource, Releasable):
	def _release(self):
		pass
