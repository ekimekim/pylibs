
"""Experimenting with concatenative programming

Usage:

Declare a 'conc', a concatenative object, by wrapping a function.
This function should take (input, output) queues as the first two args,
with any remaining args being passed through from its creation later.

For example, a conc that adds an arg n to every input and sends it to the output:

	@conc
	def add_n(input, output, n):
		for item in input:
			output.put(item + n)

Create a specific instance of a conc by calling it:

	add_two = add_n(2)

You can "pipe" concs (join the output of A to the input of B) with the syntax "A|B", eg.

	add_three = add_n(1) | add_n(2)

Note that add_three is also a conc.

When you're ready, call your conc with .run()
A conc with no input will read the null input, ie. an empty queue.
A conc with no output will return the final output queue, suitable for iterating over.

Using our example above and the crange() conc which acts like range() but yields items to its output:

	>>> list((crange(5) | add_three).run())
	[3, 4, 5, 6, 7]

Many concs come predefined.

NOTE: Uses gevent for executing all the conc bodies concurrently.
"""

import functools
import re
import sys

import gevent.pool
import gevent.queue


def conc(fn):
	"""Decorator to define a conc. See module help for details."""
	@functools.wraps(fn)
	def _conc_wrapper(*args, **kwargs):
		return Conc([(fn, args, kwargs)])
	return _conc_wrapper


class Conc(object):
	def __init__(self, fns):
		self.fns = fns

	def __or__(self, other):
		return Conc(self.fns + other.fns)

	def run(self):
		group = gevent.pool.Group()
		last_output = ClosingQueue()
		last_output.close() # first input is an empty input queue
		for fn, args, kwargs in self.fns:
			this_output = ClosingQueue()
			group.spawn(self._run, fn, last_output, this_output, args, kwargs)
			last_output = this_output
		return last_output

	def _run(self, fn, input, output, args, kwargs):
		try:
			fn(input, output, *args, **kwargs)
		finally:
			output.close()


class ClosingQueue(gevent.queue.Queue):
	"""The queues that concs use are a special kind that can be closed.
	Once it is closed and all items consumed, any further gets will result in StopIteration,
	though note length will still report as 1.
	It is reccomended that you iterate over the queue for easy usage.
	"""
	EOF = object()
	closed = False

	def _get(self):
		if super(ClosingQueue, self)._peek() is self.EOF:
			return StopIteration
		return super(ClosingQueue, self)._get()

	def _peek(self):
		if super(ClosingQueue, self)._peek() is self.EOF:
			return StopIteration
		return super(ClosingQueue, self)._peek()

	def close(self):
		if not self.closed:
			self.closed = True
			self.put(self.EOF)


@conc
def cat(input, output):
	"""Copies input to output"""
	for item in input:
		output.put(item)

@conc
def iter_to_conc(input, output, iterable):
	"""Outputs contents of an iterator"""
	for item in iterable:
		output.put(item)


def crange(*args):
	"""As per range(), but as a conc"""
	return iter_to_conc(xrange(*args))


@conc
def cmap(input, output, func):
	"""For each input x, outputs func(x)"""
	for item in input:
		output.put(func(item))

@conc
def cfilter(input, output, func):
	"""Outputs each input x if func(x) is true"""
	for item in input:
		if func(item):
			output.put(item)

@conc
def creduce(input, output, func, initial):
	"""Applies a reduce function over inputs, then outputs final result"""
	value = initial
	for item in input:
		value = func(value, item)
	output.put(value)


def grep(pattern, flags=0):
	"""You know what this does"""
	regex = re.compile(pattern, flags)
	return cfilter(lambda s: regex.search(s))


@conc
def read(input, output, file=None):
	"""Output lines (without newline) from given file-like object. By default, reads with raw_input()"""
	if file is None:
		while True:
			try:
				line = raw_input()
			except EOFError:
				return
			output.put(line)
	else:
		for line in file:
			output.put(line.rstrip('\n'))


@conc
def write(input, output, file=sys.stdout):
	"""Write items from input to given file-like object, one per line. Default stdout."""
	for item in input:
		file.write(str(item) + '\n')
