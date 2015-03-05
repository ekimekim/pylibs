
"""Context manager for implementing rate limiting of a code block"""


class RateLimited(Exception):
	def __str__(self):
		return "The code block has been called too many times"


class RateLimit(object):
	"""Context manager which prevents code block inside from running too often.
	The means of tracking the current count of runs is done using get_count()
	and inc_count(). If get_count() exceeds the given limit, limited() is called.
	By default the limit is a hard limit for the lifetime of the object (ie. counts never
	"expire") and a RateLimited exception is raised when the limit is reached.
	However, all these functions are overridable and several useful examples are provided.

	Code is limited on entry (exit is a no-op), and you may use the run() method in place
	of a context manager if you wish, ie. the following are equivilent:
		with ratelimit:
			...
	and:
		ratelimit.run()
		...
	"""

	def __init__(self, limit):
		self.limit = limit

	def __enter__(self):
		self.run()

	def __exit__(self, *exc_info):
		pass

	def run(self):
		"""Count a run of the rate-limited code, or return self.limited() (which by default will raise)
		otherwise. Returns None if not limited (this opens it up for subclasses to return something useful
		from self.limited())"""
		if self.check_limit():
			self.inc_count()
		else:
			return self.limited()

	def check_limit(self):
		"""Return boolean of whether count exceeds (or equals) limit. By default, uses get_count() and self.limit,
		but subclasses may override (for example for limits that aren't a simple value)."""
		return self.get_count() < self.limit

	def get_count(self):
		"""Return count of number of calls of the limited code.
		By default, returns self.count (if it exists, else 0)"""
		return getattr(self, 'count', 0)

	def inc_count(self):
		"""Add one to the count of number of calls of the limited code.
		By default, sets self.count to get_count() + 1"""
		self.count = self.get_count() + 1

	def limited(self):
		"""Called when the code is limited. By default, raises RateLimited"""
		raise RateLimited

	def time_left(self):
		"""An optional method which subclasses may implement to estimate the time left
		until the code may be run. There are no guarentees as to the accuracy of this value.
		It is intended as for either a retry rate or user display.
		It should not be negative."""
		raise NotImplementedError


class TimeBlockRateLimit(RateLimit):
	"""A RateLimit where runs are "forgotten" after each time interval.
	For example, limit=10 and interval=60 would only allow 10 runs in each minute.
	However, this limit could still be exceeded over shorter time periods, for example
	if it was run 10 times at 00:59 and 10 times at 01:01.
	This implementation uses wall clock time, which may cause inaccuracies
	when the system time jumps."""
	time_block = None
	count = 0

	def __init__(self, limit, interval):
		"""Interval must be in seconds."""
		super(TimeBlockRateLimit, self).__init__(limit)
		self.interval = interval

	def time_block_changed(self):
		"""Return True if time block is not same as saved time block (and update saved block)"""
		import time
		time_block = int(time.time() / self.interval)
		if self.time_block == time_block:
			return False
		self.time_block = time_block
		return True

	def get_count(self):
		if self.time_block_changed:
			self.count = 0
		return self.count

	def time_left(self):
		import time
		return max(0, (self.time_block + 1) * self.interval - time.time())


class DecayRateLimit(RateLimit):
	"""A RateLimit which operates on an exponential decay counter, allowing a more natural
	rate limiting which can clamp spikes but is more tolerant of sustained usage.
	For example, with limit=10 and halflife=60, you could do 10 runs, then 5 every minute thereafter.
	Alternately, you could do 10 runs then one every 9 seconds or so (equivilent to ~6.5 a minute).
	Note that using this implementation requires the decay module.
	"""
	def __init__(self, limit, halflife):
		from decay import DecayCounter
		self.limit = limit
		self.count = DecayCounter(halflife)

	def get_count(self):
		return self.count.get()

	def inc_count(self):
		self.count.add(1)

	def time_left(self):
		import math
		target_ratio = self.get_count() / self.limit
		return max(0, self.count.halflife * math.log(target_ratio, 2))


class BlockingRateLimit(RateLimit):
	"""Uses gevent and the time_left method to block until the rate limited code may proceed.
	If used with multiple inheritance, ensure it is the final class in the MRO.
	Note that this implementation requires gevent.
	"""

	def check_limit(self):
		import gevent
		while not super(BlockingRateLimit, self).check_limit():
			gevent.sleep(self.time_left())
		return True
