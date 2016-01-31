
"""A queue which supports low-cardinality priorities, with FIFO within each priority level"""

from collections import defaultdict, deque

import gevent.queue

__REQUIRES__ = ['gevent']

class ChunkedPriorityQueue(gevent.queue.Queue):
	"""A subclass of Queue that ONLY takes items of the form (priority, data).
	A lower priority item will always be returned before a higher one.
	Unlike gevent.queue.PriorityQueue, two items with equal priority are fetched in order.
	It is generally expected that priorities be integers, though any hashable value is allowed
	as long as all priorities are comparable.
	This implementation does not expect large numbers of unique priorities, and performance
	will suffer if used in this way.

	As a special extension, the queue can be "cut off" so only messages better or equal to a given priority
	will be fetched. Note the queue's apparent size will change.
	This can be done by using "with queue.limit_to(limit):".
	If multiple limits are put in place, only the lowest applies.
	A global limit outside any context manager is also able to be set with queue.set_limit()
	"""

	# Implementation: self.queue is a dict {priority: deque}

	limit = None

	def _init(self, maxsize, items=[]):
		self.queue = defaultdict(deque)
		self._limits = {}
		for item in items:
			self._put(item)

	def qsize(self):
		limit = self.get_limit()
		return sum(len(queue) for priority, queue in self.queue.items()
				   if limit is None or priority <= limit)

	def _put(self, item):
		priority, data = item
		self.queue[priority].append(data)

	def _find_next(self):
		limit = self.get_limit()
		for priority, queue in sorted(self.queue.items()):
			if limit is not None and priority > limit:
				break
			if queue:
				return priority, queue
		assert False, "_find_next called with all queues empty"

	def _get(self):
		priority, queue = self._find_next()
		return priority, queue.popleft()

	def _peek(self):
		priority, queue = self._find_next()
		return priority, queue[0]

	def get_limit(self):
		return min(self._limits.values()) if self._limits else None

	def set_limit(self, limit):
		"""Sets base limit, or None to unset. Can still be made lower by limit_to() limits"""
		if limit is None:
			self._limits.pop(None, None)
		else:
			self._limits[None] = limit
		# try to unblock any pending gets
		self._schedule_unlock()

	def limit_to(self, limit):
		"""Apply a limit for the duration of a code block"""
		parent = self
		class _LimitContext(object):
			def __enter__(self):
				parent._limits[self] = limit
			def __exit__(self, *exc_info):
				del parent._limits[self]
				# try to unblock any pending gets
				parent._schedule_unlock()
		return _LimitContext()

