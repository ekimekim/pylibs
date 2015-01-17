
IDENTITY = lambda x: x

class Pool(object):
	"""Implements a generic pool of resources.
	The resource is an object that:
	* is created by the given factory function / class
	* is intended to be re-used
	* is hashable and unique (ie. multiple calls to factory() won't return the same object)
	* optionally, gets prepared for re-use by given clean_fn
	* optionally, is destroyed by given destroy_fn

	Usage:
		pool = Pool(lambda: get_a_thing(...), destroy_fn=lambda thing: thing.close())

		thing = pool.get()
		...
		pool.put(thing)

		with pool.get() as thing:
			...
		# auto puts thing back

		pool.destroy_all()

	This pool is gevent-safe but not thread-safe.
	"""

	def __init__(self, factory, clean_fn=IDENTITY, destroy_fn=IDENTITY,
	             min=None, max=None, limit=None):
		"""Create a new Pool containing objects as returned from factory()
		Optional args:
			clean_fn: An optional fn that is used to "reset" used resources to a clean state.
			          If defined, it should take one arg (the resource) and return the modified resource.
			destroy_fn: An optional fn that is used to properly dispose of a resource. For example,
			            it might close a connection or kill a thread. If defined, it should take the resource
			            as its only arg.
			min: If defined, pool will be pre-populated with at least this many members.
			max: If defined, any excess members over this number that the pool creates
			     to deal with high load will be destroyed when no longer in use.
			limit: If defined, this is an absolute hard limit on the number of members, in use or otherwise.
		"""
		self.members = []
		self.used = set()
		self.to_clean = []
		self.cleaning = set()
		self.creating = 0

		self.factory = factory
		self.clean_fn = clean_fn
		self.destroy_fn = destroy_fn
		self.min = min
		self.max = max
		self.limit = limit

		self._ensure_min()

	@property
	def available(self):
		return [x for x in self.members if x not in (self.used | self.cleaning | set(self.to_clean))]

	def get(self):
		"""Get a resource. Returned object is actually a wrapped version of the resource
		which allows a context manager (with clause) which returns the resource to the pool on exit.
		"""
		if not self.available and not self.clean(destroy=False):
			if self.limit is not None and len(self.members) + self.creating >= self.limit:
				raise PoolExhaustedException()
			self.create()
		assert self.available, "Still no resources available after making one available"
		resource = self.available[0]
		self.used.add(resource)
		return self._wrap(resource)

	def put(self, resource):
		"""Return a resource previously taken from the pool."""
		if isinstance(resource, ResourceWrapper):
			resource = resource.__resource
		if resource not in self.members:
			raise ValueError("Given resource is not owned by this pool")
		if resource not in self.used:
			raise ValueError("Given resource is not in use")
		self.to_clean.append(resource)

	def adopt(self, resource, in_use=False):
		"""Explicitly add a given resource into the pool.
		If in_use=True, resource is initally listed as in use and must be put() before it becomes available.
		WARNING: This function can be used to push the total membership over pool.limit
		"""
		self.members.insert(0, resource)
		if in_use:
			self.used.add(resource)

	def remove(self, resource):
		"""Fully remove resource from the pool. The pool completely forgets about the resource and it
		can no longer be put() back (though you could re-introduce it with adopt()).
		"""
		if isinstance(resource, ResourceWrapper):
			wrapper, resource = resource, resource.__resource
			wrapper.__pool = None
		if resource not in self.members:
			raise ValueError("Given resource is not owned by this pool")
		for collection in (self.to_clean, self.used, self.members):
			if resource in collection:
				collection.remove(resource)
		# create back up to min if needed
		self._ensure_min()

	def destroy(self, resource):
		"""Destroy resource, removing it from the pool and calling the destroy callback."""
		self.remove(resource)
		self.destroy_fn(resource)

	def clean(self, destroy=True):
		"""Tell pool to clean a resource (if any need cleaning) and make it available.
		Note this function never needs to be called as resources are cleaned on demand,
		but you may want to call it explicitly to prevent needing to do it later.
		Note that, if we have exceeded self.max, we destroy the resource instead of cleaning it
		(unless destroy=False, which might be useful if you know the high demand is not over).
		Returns True if any cleaning was actually done, otherwise False.
		eg. to clean all pending resources, you might use:
			while pool.clean(): pass
		In particular, we guarentee that at least one resource will be available if destroy=False
		and the return value is True.
		"""
		if not self.to_clean:
			return False
		resource = self.to_clean.pop(0)
		self.cleaning.add(resource)
		if destroy and self.max is not None and len(self.members) > self.max:
			self.destroy(resource)
			return True
		cleaned = self.clean_fn(resource)
		assert resource in self.members, "Resource to clean not owned by pool"
		self.members.remove(resource)
		self.members.append(cleaned)
		return True

	def create(self):
		"""Explicitly tell the pool to generate a new resource now.
		Note this function never needs to be called as resources are created on demand,
		but you may want to call it explicitly to prevent needing to do it later.
		However, in most cases you should probably use the min argument to __init__ instead.
		WARNING: This function can be used to push the total membership over pool.limit
		"""
		self.creating += 1
		try:
			self.adopt(self.factory())
		finally:
			self.creating -= 1

	def destroy_all(self):
		"""Destroy all resources. The pool should not be used after this is called."""
		members = self.members[:]
		while members:
			self.destroy(members[0])

	def _ensure_min(self):
		"""Ensure we have at least self.min members"""
		if self.min is None: return
		while len(self.members) < self.min:
			self.create()

	def _wrap(self, resource):
		"""Wrap a resource in a ResourceWrapper"""
		return ResourceWrapper(self, resource)


class ResourceWrapper(object):
	"""This is the wrapper that wraps returned resources.
	Note that currently the wrapper isn't very sophisticated, and only fakes
	attribute access. Special features like isinstance() or operators will not behave correctly.
	"""
	def __init__(self, pool, resource):
		self.__pool = pool
		self.__resource = resource

	def __getattr__(self, attr):
		return getattr(self.__resource, attr)
	def __setattr__(self, attr, value):
		return setattr(self.__resource, attr, value)

	def __enter__(self):
		pass

	def __exit__(self, *exc_info):
		if not self.__pool: return
		self.__pool.put(self)


class PoolExhaustedException(Exception):
	pass
