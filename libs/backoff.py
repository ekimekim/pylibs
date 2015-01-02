
"""Simple backoff generator

An exponential backoff generator.
Will give exponentially higher numbers (with a small random factor) up to limit, until reset is called.
"""


import random


class Backoff(object):
	start = 1 # first value
	limit = 100 # max value
	rate = 2 # factor to multiply by each step
	jitter = 0.01 # random multiple of current value to modify each step by

	def __init__(self, start=None, limit=None, rate=None, jitter=None):
		"""Values may override class attributes"""
		if start is not None:
			self.start = start
		if limit is not None:
			self.limit = limit
		if rate is not None:
			self.rate = rate
		if jitter is not None:
			self.jitter = jitter
		self.reset()

	def reset(self):
		"""Set the next value back to start"""
		self.value = self._do_jitter(self.start)

	def get(self):
		"""Get the next value and increase value"""
		value = self.value
		self.value = self._do_jitter(min(self.limit, value * self.rate))
		return value

	def peek(self):
		"""Get the next value without modifying it"""
		return self.value

	def _do_jitter(self, value):
		return value + (random.random() - .5) * self.jitter * value
