
"""Implements a counter whose value decays over time

DecayCounter() objects store a float, which decays over time with the given decay rate.
Decay rate is expressed as a half-life, ie. after half_life seconds, the value is halved.
The decay is automatically accounted for on a get() operation, no background thread or other out-of-band
timekeeping is used.

Note that while a set() operation is provided, it is not safe to use in a read-modify-write pattern,
as you would lose the decay that should have occurred between the read and the write.
You should instead use modify() for such operations, which takes a callable that should perform the operation
and return the result.

If one of the following libraries is installed, monotonic time will be used by default:
	Monotime
	Monoclock
	monotonic
If you would like to enforce this as a requirement, use the monotonic=True flag.
Conversely, if you would like to force the use of wall clock time.time() even when monotonic is available,
use monotonic=False. Note this is probably a bad idea
(for example, your values will jump up wildly if the system time is changed backwards).
"""

import math
import time
from importlib import import_module


# lib name, function that gets value given module (in order of preference)
_monotonic_libs = [
	('monotonic', lambda module: module.monotonic()),
	('monotime', lambda module: module.monotonic()),
	('monoclock', lambda module: module.nano_count() / 1e9),
]

for _lib, _fn in _monotonic_libs:
	try:
		_monotonic_module = import_module(_lib)
	except (ImportError, RuntimeError): # "monotonic" will raise RuntimeError if no implementation for platform
		continue
	has_monotonic = True
	monotonic_time = lambda: _fn(_monotonic_module)
	break
else:
	has_monotonic = False


class DecayCounter(object):
	"""Holds a value that decays over time.
	"""

	def __init__(self, halflife, initial=0, monotonic=None):
		"""Half-life is expressed in seconds.
		If monotonic is given and True, force the use of monotonic time or fail with ValueError().
		If monotonic is given and False, force the use of time.time() even if monotonic time is available.
		If monotonic is not given, use monotonic time if available, else time.time().
		"""
		if monotonic and not has_monotonic:
			raise ValueError("System does not support monotonic time")
		self._halflife = halflife
		self._monotonic = has_monotonic if monotonic is None else monotonic
		self._update(initial, self._get_time())

	@property
	def halflife(self):
		return self._halflife
	@halflife.setter
	def halflife(self, halflife):
		# we want to apply the old half life up until now, then change it.
		value, time = self._get()
		self._update(value, time)
		self._halflife = halflife

	def get(self):
		"""Returns the current value, taking into account any decay since last set"""
		value, time = self._get()
		return value

	def modify(self, func):
		"""Safely read, modify, then write the value. Func should be a callable that takes one arg,
		the current value, and returns the new value.
		For example:
			def double(counter):
				counter.modify(lambda value: value * 2)
		"""
		value, time = self._get()
		value = func(value)
		self._update(value, time)

	def copy(self):
		"""Return a new instance of DecayCounter() with the same halflife as the current counter,
		and initially the same value."""
		return DecayCounter(self.halflife, self.get(), monotonic=self._monotonic)

	def set(self, value):
		"""Sets the value. Note that this method is only safe when setting to a constant value
		ie. it is not safe to read the value, modify it, then set it. This will cause there to be no
		decay applied for the period of time between your get() and your set()."""
		# As it turns out, set is really just a special case of modify
		self.modify(lambda old: value)

	def add(self, amount):
		"""Add amount to value (amount can be negative). A shortcut for modify(lambda value: value + amount)."""
		self.modify(lambda value: value + amount)

	def _get_time(self):
		"""Returns the current time, by whatever counting method is in use.
		Subclasses should override this to implement alternate timekeeping.
		"""
		return monotonic_time() if self._monotonic else time.time()

	def _get(self):
		"""Returns the current value, along with the point in time when that value was taken"""
		# We calculate the current value based on decay and time since last set
		# We could update on every get, but there's no need (and I suspect it might lead to floating
		#  point errors if you get() in rapid succession)
		decay_exponent = -math.log(2) / self.halflife
		current_time = self._get_time()
		elapsed = current_time - self._time
		current_value = self._value * math.exp(decay_exponent * elapsed)
		return current_value, current_time

	def _update(self, value, time):
		"""Underlying function that updates the value and time"""
		self._value = value
		self._time = time
