import queue
import threading
import time
from typing import Callable, List, Tuple
import collections
from rate_limiters import RateLimiter, FixedWindowRateLimiter

class BatchProcessor:
    def __init__(self, num_executors=2, rate_limit_mode="unlimited", max_rpm=0, max_tpm=0):
        self.task_queue = queue.Queue()
        self.lock = threading.Lock()
        self.rate_limiter_lock = threading.Lock()  # Dedicated lock for rate limiter access
        self.executors = []
        self.rate_limit_mode = rate_limit_mode
        self.rate_limiter = None
        if rate_limit_mode == "limited":
            self.rate_limiter = FixedWindowRateLimiter(max_rpm=max_rpm, max_tpm=max_tpm)
        self.reset(num_executors)
    
    def add_task(self, task_func: Callable, *args, **kwargs):
        """Add a task to the processing queue."""
        self.task_queue.put((task_func, args, kwargs))
        with self.lock:
            self.total_tasks += 1
    
    def _executor_worker(self, executor_id: int):
        """Worker method executed by each executor thread to process tasks."""
        while self.running:
            try:
                # Try to get a task with timeout
                task_func, args, kwargs = self.task_queue.get(timeout=0.5)
                
                # Check rate limits if in limited mode
                if self.rate_limit_mode == "limited" and self.rate_limiter:
                    # Check if we should limit this request
                    with self.rate_limiter_lock:
                        should_limit = self.rate_limiter.should_limit()
                    
                    # If we should limit, put the task back in the queue and move on
                    if should_limit:
                        # Put the task back into the queue
                        self.task_queue.put((task_func, args, kwargs))
                        with self.lock:
                            self.requeued_tasks += 1
                        self.task_queue.task_done()
                        continue  # Skip to the next task
                
                # Execute the task
                start_time = time.monotonic()
                task_result = None
                error = None
                requeued = False
                
                try:
                    # Record query timestamp before making the API call
                    with self.lock:
                        self.query_history.append(time.time())
                        self.queries_since_last_calculation += 1
                    
                    # Execute the task
                    task_result = task_func(*args, **kwargs)
                    
                    # If using rate limiting, record the successful request with tokens
                    if self.rate_limit_mode == "limited" and self.rate_limiter:
                        tokens = task_result.get('tokens', 0) if task_result else 0
                        # Use dedicated lock to ensure atomic rate limiter update
                        with self.rate_limiter_lock:
                            self.rate_limiter.record_request(tokens)
                        
                except Exception as e:
                    error = str(e)
                    # Check if it's a rate limit error
                    if "429" in error and "rate limit" in error.lower():
                        # Put the task back into the queue
                        self.task_queue.put((task_func, args, kwargs))
                        requeued = True
                        with self.lock:
                            self.requeued_tasks += 1
                
                execution_time = time.monotonic() - start_time
                
                # Store result unless it was requeued
                if not requeued:
                    with self.lock:
                        self.results.append({
                            'executor_id': executor_id,
                            'task_result': task_result,
                            'execution_time': execution_time,
                            'error': error,
                            'status': 'error' if error else 'success'
                        })
                        self.completed_tasks += 1
                        if error:
                            self.error_count += 1
                        else:
                            # Record timestamp for successful requests (RPM calculation)
                            self.request_history.append(time.time())
                            
                        # Track tokens if available in the result
                        if not error and task_result and 'tokens' in task_result:
                            tokens = task_result['tokens']
                            self.total_tokens += tokens
                            # Update token statistics
                            self.min_tokens = min(self.min_tokens, tokens)
                            self.max_tokens = max(self.max_tokens, tokens)
                            self.token_count += 1
                            # Record timestamp and tokens for TPM calculation
                            self.token_history.append((time.time(), tokens))
                
                self.task_queue.task_done()
            except queue.Empty:
                # No tasks available, continue
                pass
    
    def start(self):
        """Start executor threads to begin processing tasks."""
        self.running = True
        self.executors = []
        self.results = []
        self.completed_tasks = 0
        self.error_count = 0
        self.requeued_tasks = 0
        
        # Reset rate limiter state if it exists
        if self.rate_limiter:
            with self.rate_limiter_lock:
                self.rate_limiter.reset()
        
        for i in range(self.num_executors):
            thread = threading.Thread(
                target=self._executor_worker, 
                args=(i,), 
                daemon=True
            )
            self.executors.append(thread)
            thread.start()
    
    def stop(self):
        """Stop all executor threads gracefully."""
        self.running = False
        for thread in self.executors:
            if thread.is_alive():
                thread.join(1.0)

    def reset(self, num_executors=2):
        """Reset the processor state and optionally set a new number of executors."""
        self.stop()
        self.task_queue.queue.clear()
        self.num_executors = num_executors
        self.executors = []
        self.results = []
        self.completed_tasks = 0
        self.total_tasks = 0
        self.error_count = 0
        self.requeued_tasks = 0
        self.total_tokens = 0
        self.min_tokens = float('inf')
        self.max_tokens = 0
        self.token_count = 0
        self.token_history = collections.deque()
        self.request_history = collections.deque()
        self.query_history = collections.deque()
        self.tpm_window_seconds = 60
        self.rpm_window_seconds = 10
        self.last_qps_calculation_time = time.time()
        self.queries_since_last_calculation = 0
        self.instantaneous_qps = 0.0
        self.running = False
        
        # Reset rate limiter if it exists
        if self.rate_limiter:
            with self.rate_limiter_lock:
                self.rate_limiter.reset()
        
    def set_rate_limits(self, mode="unlimited", max_rpm=0, max_tpm=0):
        """Update rate limiting settings."""
        self.rate_limit_mode = mode
        
        with self.rate_limiter_lock:
            if mode == "limited":
                if self.rate_limiter:
                    self.rate_limiter.max_rpm = max_rpm
                    self.rate_limiter.max_tpm = max_tpm
                    self.rate_limiter.reset()  # Reset state when changing limits
                else:
                    self.rate_limiter = FixedWindowRateLimiter(max_rpm=max_rpm, max_tpm=max_tpm)
            else:
                self.rate_limiter = None

    def _calculate_tpm(self):
        """Calculate tokens per minute based on a sliding window."""
        if not self.token_history:
            return 0
            
        current_time = time.time()
        window_start = current_time - self.tpm_window_seconds
        
        # Remove entries older than our window
        while self.token_history and self.token_history[0][0] < window_start:
            self.token_history.popleft()
        
        # If no entries within our window, return 0
        if not self.token_history:
            return 0
        
        # Sum up tokens in our window
        tokens_in_window = sum(tokens for _, tokens in self.token_history)
        
        # If we have entries but they're all very recent,
        # extrapolate to get a more accurate estimate
        window_duration = current_time - self.token_history[0][0]

        # Calculate tokens per minute using the actual window duration
        tpm = (tokens_in_window / window_duration) * 60
        return int(tpm)

    def _calculate_rpm(self):
        """Calculate requests per minute based on a sliding window."""
        if not self.request_history:
            return 0
            
        current_time = time.time()
        window_start = current_time - self.rpm_window_seconds
        
        # Remove entries older than our window
        while self.request_history and self.request_history[0] < window_start:
            self.request_history.popleft()
        
        # If no entries within our window, return 0
        if not self.request_history:
            return 0
        
        # Calculate requests per minute using the actual window duration
        window_duration = current_time - self.request_history[0]
        if window_duration < 1:  # Avoid division by very small numbers
            return 0
            
        rpm = (len(self.request_history) / window_duration) * 60
        return int(rpm)

    def _calculate_qps(self):
        """Calculate instantaneous queries per second."""
        current_time = time.time()
        time_diff = current_time - self.last_qps_calculation_time
        
        # Ensure we don't divide by a very small number
        if time_diff >= 0.1:  # Only update if at least 0.1 seconds have passed
            if self.queries_since_last_calculation > 0:
                self.instantaneous_qps = self.queries_since_last_calculation / time_diff
            else:
                self.instantaneous_qps = 0
            
            # Reset counters
            self.last_qps_calculation_time = current_time
            self.queries_since_last_calculation = 0
        
        return round(self.instantaneous_qps, 2)  # Round to 2 decimal places for readability

    def get_progress(self):
        """Retrieve current progress metrics of task processing."""
        with self.lock:
            # Calculate average tokens per task
            avg_tokens = 0
            if self.token_count > 0:
                avg_tokens = round(self.total_tokens / self.token_count)
                
            # Handle edge case of no tasks completed yet
            min_tokens = 0 if self.min_tokens == float('inf') else self.min_tokens
            
            # Get rate limiter info if active
            rate_limit_info = {}
            if self.rate_limit_mode == "limited" and self.rate_limiter:
                with self.rate_limiter_lock:
                    rate_limit_info = self.rate_limiter.get_current_rates()
                
            return {
                'completed': self.completed_tasks,
                'total': self.total_tasks,
                'queue_size': self.task_queue.qsize(),
                'results': self.results.copy(),
                'error_count': self.error_count,
                'requeued_tasks': self.requeued_tasks,
                'total_tokens': self.total_tokens,
                'min_tokens': min_tokens,
                'max_tokens': self.max_tokens,
                'avg_tokens': avg_tokens,
                'tpm': self._calculate_tpm(),
                'rpm': self._calculate_rpm(),
                'qps': self._calculate_qps(),
                'rate_limit_mode': self.rate_limit_mode,
                'rate_limit_info': rate_limit_info
            }
        
    def remaining_tasks(self):
        """Return the number of tasks remaining in the queue."""
        with self.lock:
            return self.total_tasks - self.completed_tasks