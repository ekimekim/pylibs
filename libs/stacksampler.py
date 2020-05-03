
import atexit
import signal


class SiftCounter(object):
	"""SiftCounter is a specialized counter (that maps value -> count) in order
	to emphasise the following operations:
	* Incrementing a value
	* Returning a list of the top N values
	It does this by maintaining a list of (value, count) sorted descending on count.
	This allows for a trivial look up of the first N values, however,
	some more work is needed to ensure increment is still fast:
	* We maintain a secondary index of {value: index into list of value}, allowing fast
	  finding of the relevant value if it exists.
	* If it does not, we add it to the end with a count of 0 and proceed as otherwise.
	* We can then increment the value in-place. However, we now need to re-establish
	  the sort invariant.
	* We do this by "sifting" the value upward, copying all earlier index values down by 1
	  until we find a count that is greater than our new count. We then write our incremented
	  value there. This is O(n), but crucially n is the number of values such that:
	    our old count <= their count < our new count
	  and since we're only ever incrementing by a very small, fixed number,
	  n should remain extremely small in all cases.

	A very basic benchmark on 100k unique items gives sub-1us increment times.
	"""
	def __init__(self, initial={}):
		"""Initial, if given, should be a dict mapping {value: count}"""
		self.counts = sorted(initial.items(), key=lambda t: t[1], reverse=True)
		self.by_value = {}
		for index, (value, count) in enumerate(self.counts):
			self.by_value[value] = index

	def __len__(self):
		return len(self.counts)

	def top(self, n):
		"""Return top N values as (value, count)"""
		return self.counts[:n]

	def increment(self, value, amount=1):
		# Look up value position, or add value onto the end if new
		if value in self.by_value:
			index = self.by_value[value]
			check_value, count = self.counts[index]
			count += amount
			assert value == check_value
		else:
			# This value will be replaced anyway, we're just physically extending the list
			index = len(self.counts)
			count = amount
			self.counts.append(None)

		# Walk up the list, copying elements down as we go,
		# until we find the first element bigger than (or equal to) count,
		# or the head of the list.
		while index > 0 and self.counts[index - 1][1] < count:
			# Move element down one
			self.counts[index] = self.counts[index - 1]
			# Fix up by_value
			self.by_value[self.counts[index][0]] = index
			# Repeat for next index
			index -= 1

		# We've reached our new position. Note we might not have even moved at all.
		self.counts[index] = (value, count)
		# Fix up by_value
		self.by_value[value] = index


class StackSampler(object):
	"""Samples the stack every INTERVAL seconds of user time.
	We could use user+sys time but that leads to interrupting syscalls,
	which may affect performance, and we care mostly about user time anyway.

	Call report() to get a sequence of (stack, count). Note this does NOT reset the count,
	counts are cumulative over the entire period stacks are collected.
	NOTE: Stack counts include all their children.

	Call stop() to stop collecting.

	NOTE: Uses the SIGVTALRM signal and the ITIMER_VIRTUAL timer,
	and will conflict with other usage.
	"""
	def __init__(self, interval=0.005):
		self.counts = SiftCounter()
		self.interval = interval
		signal.signal(signal.SIGVTALRM, self.sample)
		# deliver the first signal in INTERVAL seconds
		signal.setitimer(signal.ITIMER_VIRTUAL, interval)

	def sample(self, signum, frame):
		"""SIGVTALRM handler. Record stack and increment appropriate counter."""
		# Note we only start each next timer once the previous timer signal has been processed.
		# There are two reasons for this:
		# 1. Avoid handling a signal while already handling a signal, however unlikely,
		#    as this could lead to a deadlock due to locking inside prometheus_client.
		# 2. Avoid biasing the results by effectively not including the time taken to do the actual
		#    stack sampling.

		# Walk back frame pointers to build stack (in reverse order, from callee to caller)
		stack = []
		while frame is not None:
			stack.append(frame)
			frame = frame.f_back

		# format each frame as FUNCTION(MODULE)
		stack = [
			"{}({})".format(frame.f_code.co_name, frame.f_globals.get('__name__'))
			for frame in stack[::-1]
		]

		# increment counter at each level of the stack (caller to callee),
		# ensuring that values always include their children
		for i in range(len(stack)):
			# increase counter by interval, so final units are in milliseconds
			self.counts.increment(";".join(stack[:i+1]), self.interval * 1000)

		# schedule the next signal
		signal.setitimer(signal.ITIMER_VIRTUAL, self.interval)

	def count(self, stack, amount):
		"""Increment count of stack by amount"""
		self.counts[stack] += amount

	def stop(self):
		"""Stop collecting samples"""
		# Cancel pending timer
		signal.setitimer(signal.ITIMER_VIRTUAL, 0)

	def report(self, top=None):
		"""Returns a list of (stack, count) tuples.
		If top is given, only return the largest TOP entries.
		"""
		if top is None:
			top = len(self.counts)
		return self.counts.top(top)


def install(filepath=None, interval=0.005, top=None):
	"""Samples the stack every INTERVAL seconds of user time, outputing to filepath (if given) on SIGUSR1 or exit.
	If top > 0, report approximate time spent in up to TOP unique stacks.
	The limit is intended to avoid a large number of rare or irrelevant stacks from blowing out storage
	or making output take a long time.
	We could use user+sys time but that leads to interrupting syscalls,
	which may affect performance, and we care mostly about user time anyway.
	"""
	sampler = None

	def finish():
		sampler.stop()
		print "outputting", len(sampler.counts)
		output()

	def output(*args):
		if filepath is None:
			return
		counts = un_cumulative(sampler.report(top=top))
		with open(filepath, 'w') as f:
			for key, count in counts:
				f.write("{} {}\n".format(key, count))

	def un_cumulative(counts):
		"""Takes a list of (stack, count) in sorted order (largest first)
		and modifies it so that parent values do not also count their children.
		Yields (stack, count)."""
		counts = counts[::-1] # guarentee children come before parents
		to_remove = {} # {stack: amount to remove}
		for stack, count in counts:
			adjusted_count = count - to_remove.pop(stack, 0)
			yield stack, adjusted_count
			if ';' not in stack:
				continue
			parent, _ = stack.rsplit(';', 1)
			to_remove[parent] = to_remove.get(parent, 0) + count
		assert not to_remove, "unseen parents: {}".format(to_remove)

	atexit.register(finish)
	signal.signal(signal.SIGUSR1, output)

	sampler = StackSampler(interval=interval)


if __name__ == '__main__':
	# Simple test
	import random, argh

	def main(filepath, interval=0.005, top=0):
		if top == 0:
			top = None

		def both(n):
			if n:
				if random.random() < .25:
					less(n-1)
				else:
					more(n-1)

		def less(n):
			both(n)

		def more(n):
			both(n)

		install(filepath, interval=interval, top=top)
		while True:
			both(50)

	argh.dispatch_command(main)
