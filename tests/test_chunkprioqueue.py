
from unittest import TestCase, main

from gevent.queue import Empty

from chunkprioqueue import ChunkedPriorityQueue

class ChunkedPriorityQueueTests(TestCase):

	def test_basic(self):
		queue = ChunkedPriorityQueue()
		queue.put((1, 'foo'))
		queue.put((1, 'bar'))
		self.assertEquals(queue.get(), (1, 'foo'))
		queue.put((0, 'baz'))
		self.assertEquals(queue.get(), (0, 'baz'))
		self.assertEquals(queue.get(), (1, 'bar'))

	def test_limit(self):
		queue = ChunkedPriorityQueue()
		queue.put((0, 'foo'))
		queue.put((1, 'bar'))
		queue.set_limit(0)
		self.assertEquals(queue.get(), (0, 'foo'))
		self.assertRaises(Empty, lambda: queue.get(block=False))
		queue.set_limit(None)
		self.assertEquals(queue.get(), (1, 'bar'))

	def test_limit_context(self):
		queue = ChunkedPriorityQueue()
		queue.put((0, 'foo'))
		queue.put((1, 'bar'))
		with queue.limit_to(0):
			with queue.limit_to(-1):
				self.assertRaises(Empty, lambda: queue.get(block=False))
			self.assertEquals(queue.get(), (0, 'foo'))
			self.assertRaises(Empty, lambda: queue.get(block=False))
		self.assertEquals(queue.get(), (1, 'bar'))


if __name__ == '__main__':
	main()
