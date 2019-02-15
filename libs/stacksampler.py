
import atexit
import signal
from collections import Counter

def install(filepath, interval=0.005):
	"""Samples the stack every INTERVAL seconds of user time, outputing to filepath on SIGUSR1 or exit.
	We could use user+sys time but that leads to interrupting syscalls,
	which may affect performance, and we care mostly about user time anyway.
	"""
	samples = Counter()

	def sample(signum, frame):
		stack = []
		while frame is not None:
			stack.append(frame)
			frame = frame.f_back
		# format each frame as FUNCTION(MODULE)
		stack = ";".join(
			"{}({})".format(frame.f_code.co_name, frame.f_globals.get('__name__'))
			for frame in stack[::-1]
		)
		# increase counter by interval, so final units are in milliseconds
		samples[stack] += interval * 1000
		# schedule the next signal
		signal.setitimer(signal.ITIMER_VIRTUAL, interval)

	def finish():
		signal.setitimer(signal.ITIMER_VIRTUAL, 0)
		output()

	def output(*args):
		with open(filepath, 'w') as f:
			for key, count in samples.items():
				f.write("{} {}\n".format(key, count))

	atexit.register(finish)

	signal.signal(signal.SIGVTALRM, sample)
	signal.signal(signal.SIGUSR1, output)
	# deliver the first signal in INTERVAL seconds
	signal.setitimer(signal.ITIMER_VIRTUAL, interval)

