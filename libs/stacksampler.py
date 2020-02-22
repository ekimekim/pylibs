
import atexit
import signal
from collections import Counter

def install(filepath=None, interval=0.005, prometheus_top_n=None):
	"""Samples the stack every INTERVAL seconds of user time, outputing to filepath (if given) on SIGUSR1 or exit.
	If prometheus_top_n > 0, report approximate time spent in up to prometheus_top_n unique stacks as prometheus
	metric "stacksampler_user_time". If prometheus_top_n=0, all unique stacks are reported.
	The limit is intended to avoid a large number of rare or irrelevant stacks from blowing out prom storage
	or making scrapes take a long time.
	We could use user+sys time but that leads to interrupting syscalls,
	which may affect performance, and we care mostly about user time anyway.
	"""
	# Note we only start each next timer once the previous timer signal has been processed.
	# There are two reasons for this:
	# 1. Avoid handling a signal while already handling a signal, however unlikely,
	#    as this could lead to a deadlock due to locking inside prometheus_client.
	# 2. Avoid biasing the results by effectively not including the time taken to do the actual
	#    stack sampling.

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
		if filepath is None:
			return
		with open(filepath, 'w') as f:
			for key, count in samples.items():
				f.write("{} {}\n".format(key, count))

	# TODO UPTO register collector for prom to report topn samples

	atexit.register(finish)

	signal.signal(signal.SIGVTALRM, sample)
	signal.signal(signal.SIGUSR1, output)
	# deliver the first signal in INTERVAL seconds
	signal.setitimer(signal.ITIMER_VIRTUAL, interval)
