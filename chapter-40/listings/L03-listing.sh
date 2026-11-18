# 1-2. is the message in the broker? (Redis; 'celery' is the default queue name)
redis-cli -u "$REDIS_URL" LLEN celery

# 3. are workers alive, and do they know the task?
celery -A config status
celery -A config inspect registered         # is 'payments.tasks.after_payment_succeeded' listed?
celery -A config inspect active             # what is running right now
celery -A config inspect reserved           # fetched but not started: a backed-up worker
celery -A config inspect stats              # pool size, processed counts, memory

# 4. run the worker verbosely in a terminal and trigger the task
celery -A config worker -l DEBUG
